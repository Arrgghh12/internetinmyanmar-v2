"""
BGP monitor for Myanmar ASNs.
Detects route withdrawals (internet shutdowns) via RIPEstat API.
Updates Observatory JSON files in src/data/ then git-commits and pushes
so Cloudflare rebuilds the frontend automatically.

No Telegram alerts — status visible on the Observatory dashboard only.

Usage:
  python bgp_monitor.py              # check all routed MM ASNs
  python bgp_monitor.py --critical-only  # critical ASNs only (fast, every 5 min)
  python bgp_monitor.py --test       # check AS9988, print result, no file writes
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# On VPS: /root/dev/iimv2/src/data/  — the partial repo copy
# Locally: src/data/
DATA_PATH     = Path(os.getenv("DATA_PATH", "src/data"))
ASN_STATUS_FILE = DATA_PATH / "asn-status.json"
OUTAGES_FILE    = DATA_PATH / "bgp-outages.json"
HISTORY_FILE    = DATA_PATH / "bgp-history.json"

RIPESTAT_BASE = "https://stat.ripe.net/data"
IODA_BASE     = "https://api.ioda.inetintel.cc.gatech.edu/v2"

# Critical ASNs: checked every 5 min, IODA cross-checked on outage
CRITICAL_ASNS = {"AS9988", "AS132167", "AS136480", "AS58952", "AS56085"}

# Visibility thresholds
OUTAGE_THRESHOLD = 0.50   # < 50% → RED
STABLE_THRESHOLD = 0.75   # ≥ 75% → GREEN or YELLOW
STABLE_HOURS     = 1.0    # must be stable this long before turning GREEN

# Rate limiting — RIPEstat blocks concurrent bursts
REQUEST_DELAY = 0.3       # seconds between requests


# ─── RIPEstat API ─────────────────────────────────────────────────────────────

async def fetch_routed_asns(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch all routed Myanmar ASNs from RIPEstat.
    Returns list of {asn: "AS9988", name: "..."}.
    Falls back to CRITICAL_ASNS if API fails.
    """
    url = f"{RIPESTAT_BASE}/country-asns/data.json"
    try:
        resp = await client.get(url, params={"resource": "MM", "lod": 1}, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        countries = data.get("countries", [])
        routed_str = countries[0].get("routed", "") if countries else ""
        # API returns "{AsnSingle(9988), AsnSingle(132167), ...}"
        asn_numbers = re.findall(r'AsnSingle\((\d+)\)', routed_str)
        result = [{"asn": f"AS{n}", "name": f"AS{n}"} for n in asn_numbers]
        log.info("RIPEstat: %d routed MM ASNs", len(result))
        return result
    except Exception as e:
        log.warning("Could not fetch routed ASNs (%s) — using critical list", e)
        return [{"asn": asn, "name": asn} for asn in sorted(CRITICAL_ASNS)]


async def get_asn_name(asn: str, client: httpx.AsyncClient) -> str:
    """Fetch the holder/name for an ASN from RIPEstat."""
    url = f"{RIPESTAT_BASE}/as-overview/data.json"
    try:
        resp = await client.get(url, params={"resource": asn}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        holder = data.get("holder", "")
        return holder if holder else asn
    except Exception:
        return asn


async def get_routing_status(asn: str, name: str,
                              client: httpx.AsyncClient) -> dict:
    """Get current routing status for one ASN."""
    url = f"{RIPESTAT_BASE}/routing-status/data.json"
    try:
        resp = await client.get(url, params={"resource": asn}, timeout=15)
        resp.raise_for_status()
        data = resp.json()["data"]
    except Exception as e:
        return {
            "asn": asn, "name": name, "announced": False,
            "visibility_pct": 0.0, "visible_collectors": 0,
            "total_collectors": 0, "status": "RED",
            "status_since": datetime.now(timezone.utc).isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)[:80],
        }

    # API v2 uses ris_peers_seeing / total_ris_peers (no announced field)
    v4 = data.get("visibility", {}).get("v4", {})
    total   = v4.get("total_ris_peers") or v4.get("total", 0)
    visible = v4.get("ris_peers_seeing") or v4.get("visible", 0)
    pct = (visible / total) if total and total > 0 else 0.0
    # Announced = has been seen recently (last_seen exists)
    announced = bool(data.get("last_seen"))

    return {
        "asn": asn,
        "name": name,
        "announced": announced,
        "visibility_pct": round(pct, 3),
        "visible_collectors": visible,
        "total_collectors": total,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # status and status_since filled in by compute_status()
    }


async def get_ioda_status(asn: str, client: httpx.AsyncClient) -> dict:
    """Cross-check with IODA anomaly detection."""
    asn_num = asn.replace("AS", "")
    url = f"{IODA_BASE}/outages/asn/{asn_num}"
    try:
        resp = await client.get(url, params={"limit": 5}, timeout=10)
        resp.raise_for_status()
        outages = resp.json().get("data", [])
        return {"ioda_outages": len(outages), "ioda_confirmed": len(outages) > 0}
    except Exception:
        return {"ioda_outages": 0, "ioda_confirmed": False}


# ─── Status logic ─────────────────────────────────────────────────────────────

def compute_status(current: dict, previous: dict) -> tuple[str, str]:
    """
    Returns (status, status_since).
    GREEN  = up ≥ STABLE_THRESHOLD for > STABLE_HOURS
    YELLOW = up ≥ STABLE_THRESHOLD but only recently recovered (≤ STABLE_HOURS)
    RED    = down or severely degraded
    """
    pct       = current["visibility_pct"]
    announced = current["announced"]
    now_iso   = current["timestamp"]
    now       = datetime.fromisoformat(now_iso)

    prev_status = previous.get("status", "UNKNOWN")
    prev_since  = previous.get("status_since", now_iso)

    if not announced or pct < OUTAGE_THRESHOLD:
        if prev_status == "RED":
            return "RED", prev_since
        return "RED", now_iso

    if pct < STABLE_THRESHOLD:
        if prev_status in ("YELLOW", "GREEN"):
            return "YELLOW", prev_since
        return "YELLOW", now_iso

    # pct ≥ STABLE_THRESHOLD
    if prev_status == "RED" or prev_status == "UNKNOWN":
        return "YELLOW", now_iso  # just recovered — start stability timer

    if prev_status == "YELLOW":
        since = datetime.fromisoformat(prev_since)
        if (now - since).total_seconds() / 3600 >= STABLE_HOURS:
            return "GREEN", prev_since
        return "YELLOW", prev_since

    return "GREEN", prev_since


# ─── Outage event tracking (no Telegram — dashboard only) ─────────────────────

def handle_status_change(asn: str, name: str, prev_status: str,
                         curr_status: str, curr: dict, outages: list) -> list:
    if prev_status == curr_status:
        return outages

    now = datetime.now(timezone.utc)

    if curr_status == "RED" and prev_status in ("GREEN", "YELLOW"):
        # Open new outage event
        outages.append({
            "asn": asn, "name": name, "status": "DOWN",
            "started_at": now.isoformat(), "ended_at": None,
            "duration_minutes": None,
            "min_visibility_pct": curr["visibility_pct"],
            "ioda_confirmed": False, "resolved": False,
        })
        log.warning("OUTAGE opened: %s (%s)", name, asn)

    elif curr_status == "YELLOW" and prev_status == "RED":
        # Recovery — close the open outage event
        for outage in reversed(outages):
            if outage["asn"] == asn and not outage["resolved"]:
                started = datetime.fromisoformat(outage["started_at"])
                duration_min = int((now - started).total_seconds() / 60)
                outage.update({
                    "ended_at": now.isoformat(),
                    "duration_minutes": duration_min,
                    "resolved": True,
                })
                log.info("RECOVERY: %s (%s) — %d min", name, asn, duration_min)
                break

    return outages


# ─── State management ─────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── History ──────────────────────────────────────────────────────────────────

def update_history(current_statuses: dict):
    history = load_json(HISTORY_FILE, [])
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "statuses": {
            asn: {"status": s["status"], "visibility_pct": s["visibility_pct"]}
            for asn, s in current_statuses.items()
        }
    })
    save_json(HISTORY_FILE, history)


# ─── Git push ─────────────────────────────────────────────────────────────────

def _status_hash(status_file: Path) -> str:
    """Hash only the meaningful fields (status, visibility_pct, status_since) — ignore timestamps."""
    if not status_file.exists():
        return ""
    data = json.loads(status_file.read_text())
    entries = data if isinstance(data, list) else [v for v in data.values() if isinstance(v, dict)]
    key = json.dumps(
        [{"asn": e.get("asn"), "status": e.get("status"),
          "visibility_pct": e.get("visibility_pct"),
          "status_since": e.get("status_since")}
         for e in entries],
        sort_keys=True
    )
    return hashlib.md5(key.encode()).hexdigest()


def git_push_data(prev_hash: str) -> str:
    """
    Commit and push updated BGP JSON only if meaningful status changed.
    Returns the new hash (or prev_hash if nothing was pushed).
    """
    new_hash = _status_hash(ASN_STATUS_FILE)
    if new_hash == prev_hash:
        log.info("BGP data unchanged (status/visibility stable) — skipping push")
        return prev_hash

    # Walk up from agents/ to find the repo root
    here = Path(__file__).parent
    candidates = [here.parent, here.parent.parent, Path("/root/dev/iimv2")]
    repo = None
    for c in candidates:
        if (c / ".git").exists() or (c / "src" / "data").exists():
            repo = c
            break
    if repo is None:
        log.error("git push: could not find repo root")
        return prev_hash

    files = [
        str(ASN_STATUS_FILE.resolve()),
        str(OUTAGES_FILE.resolve()),
        str(HISTORY_FILE.resolve()),
    ]
    try:
        subprocess.run(["git", "-C", str(repo), "add"] + files, check=True)
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if diff.returncode == 0:
            log.info("BGP data unchanged — no git commit")
            return prev_hash
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m",
             f"data: BGP status {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"],
            check=True
        )
        subprocess.run(["git", "-C", str(repo), "pull", "--rebase", "--autostash"], check=True)
        subprocess.run(["git", "-C", str(repo), "push"], check=True)
        log.info("BGP data pushed to git → Cloudflare rebuild triggered")
        return new_hash
    except Exception as e:
        log.error("git push failed: %s", e)
        return prev_hash


# ─── Main check loop ──────────────────────────────────────────────────────────

async def check_asns(asn_list: list[dict], test_mode: bool = False):
    previous        = load_json(ASN_STATUS_FILE, {})
    outages         = load_json(OUTAGES_FILE, [])
    current_statuses = {}

    headers = {"User-Agent": "IIM-BGP-Monitor/1.0 (+https://internetinmyanmar.com)"}

    async with httpx.AsyncClient(headers=headers) as client:

        # Fetch ASN names for ones that still say "AS12345"
        # (only on full run, skip in test mode)
        if not test_mode:
            unnamed = [a for a in asn_list if a["name"] == a["asn"]]
            if unnamed:
                log.info("Fetching names for %d ASNs...", len(unnamed))
                for entry in unnamed:
                    entry["name"] = await get_asn_name(entry["asn"], client)
                    await asyncio.sleep(REQUEST_DELAY)

        # Sequential requests to avoid rate limiting
        log.info("Checking %d ASNs...", len(asn_list))
        for entry in asn_list:
            asn  = entry["asn"]
            name = entry.get("name", asn)
            result = await get_routing_status(asn, name, client)
            await asyncio.sleep(REQUEST_DELAY)

            prev = previous.get(asn, {})
            prev_status = prev.get("status", "UNKNOWN")

            # Preserve name from previous if we got a better one
            if prev.get("name") and prev["name"] != prev["asn"] and result["name"] == asn:
                result["name"] = prev["name"]

            status, status_since = compute_status(result, prev)
            result["status"]       = status
            result["status_since"] = status_since

            if test_mode:
                print(f"{asn:12} {result['name'][:40]:40} "
                      f"{status:6} {int(result['visibility_pct']*100):3}%  "
                      f"announced={result['announced']}")
                continue

            current_statuses[asn] = result
            outages = handle_status_change(
                asn, result["name"], prev_status, status, result, outages
            )

            # IODA cross-check for critical ASNs going RED
            if status == "RED" and asn in CRITICAL_ASNS and prev_status not in ("RED", "UNKNOWN"):
                ioda = await get_ioda_status(asn, client)
                result.update(ioda)
                for outage in reversed(outages):
                    if outage["asn"] == asn and not outage["resolved"]:
                        outage["ioda_confirmed"] = ioda["ioda_confirmed"]
                        break

    if test_mode:
        return

    prev_hash = _status_hash(ASN_STATUS_FILE)

    merged = {**previous, **current_statuses}
    save_json(ASN_STATUS_FILE, merged)
    save_json(OUTAGES_FILE, outages)
    update_history(current_statuses)

    down    = [s for s in current_statuses.values() if s["status"] == "RED"]
    yellow  = [s for s in current_statuses.values() if s["status"] == "YELLOW"]
    green   = [s for s in current_statuses.values() if s["status"] == "GREEN"]
    checked = len(current_statuses)

    log.info("Done: %d GREEN  %d YELLOW  %d RED  (of %d checked)",
             len(green), len(yellow), len(down), checked)

    git_push_data(prev_hash)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def run(args):
    headers = {"User-Agent": "IIM-BGP-Monitor/1.0 (+https://internetinmyanmar.com)"}

    if args.test:
        print("BGP monitor test — checking critical ASNs\n")
        test_list = [{"asn": a, "name": a} for a in sorted(CRITICAL_ASNS)]
        await check_asns(test_list, test_mode=True)
        return

    async with httpx.AsyncClient(headers=headers) as client:
        all_asns = await fetch_routed_asns(client)

    if args.critical_only:
        asn_list = [a for a in all_asns if a["asn"] in CRITICAL_ASNS]
        if not asn_list:
            asn_list = [{"asn": a, "name": a} for a in sorted(CRITICAL_ASNS)]
        log.info("Critical-only mode: %d ASNs", len(asn_list))
    else:
        asn_list = all_asns
        log.info("Full run: %d routed MM ASNs", len(asn_list))

    await check_asns(asn_list)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGP monitor for Myanmar ASNs")
    parser.add_argument("--critical-only", action="store_true",
                        help="Check only critical ASNs (fast, for 5-min cron)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: check critical ASNs, print results, no writes")
    args = parser.parse_args()
    asyncio.run(run(args))
