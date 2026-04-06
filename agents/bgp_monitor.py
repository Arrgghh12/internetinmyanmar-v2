"""
BGP monitor for Myanmar ASNs.
Detects route withdrawals (internet shutdowns) via RIPEstat API.
Updates Observatory JSON files. Fires Telegram alerts on status changes.

Usage:
  python bgp_monitor.py              # check all routed MM ASNs
  python bgp_monitor.py --critical-only  # check critical ASNs only (fast, every 5 min)
  python bgp_monitor.py --test       # check AS9988 only, print result, no file writes
"""

import argparse
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

from utils.telegram_notify import send_alert

load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OBSERVATORY_PATH = Path(
    os.getenv("OBSERVATORY_PATH", "src/content/observatory")
)
DATA_PATH        = Path(os.getenv("DATA_PATH", "src/data"))
ASN_STATUS_FILE  = DATA_PATH / "asn-status.json"
OUTAGES_FILE     = DATA_PATH / "bgp-outages.json"
HISTORY_FILE     = DATA_PATH / "bgp-history.json"

RIPESTAT_BASE = "https://stat.ripe.net/data"
IODA_BASE     = "https://api.ioda.inetintel.cc.gatech.edu/v2"

# Critical ASNs: checked every 5 min, IODA cross-checked on outage
CRITICAL_ASNS = {"AS9988", "AS132167", "AS136480", "AS58952", "AS56085"}

# Visibility thresholds
OUTAGE_THRESHOLD  = 0.50   # < 50% → RED
STABLE_THRESHOLD  = 0.75   # ≥ 75% → can be GREEN or YELLOW
STABLE_HOURS      = 1.0    # must be up this long before turning GREEN


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
        # API returns routed as a string: "{AsnSingle(9988), AsnSingle(132167), ...}"
        countries = data.get("countries", [])
        routed_str = countries[0].get("routed", "") if countries else ""
        asn_numbers = re.findall(r'AsnSingle\((\d+)\)', routed_str)
        result = [{"asn": f"AS{n}", "name": f"AS{n}"} for n in asn_numbers]
        log.info("RIPEstat returned %d routed MM ASNs", len(result))
        return result
    except Exception as e:
        log.warning("Could not fetch routed ASNs from RIPEstat (%s) — using critical list", e)
        return [{"asn": asn, "name": asn} for asn in CRITICAL_ASNS]


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

    announced = data.get("announced", False)
    v4 = data.get("visibility", {}).get("v4", {})
    total   = v4.get("total", 0)
    visible = v4.get("visible", 0)
    pct = (visible / total) if total > 0 else 0.0

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
        data = resp.json()
        outages = data.get("data", [])
        return {"ioda_outages": len(outages), "ioda_confirmed": len(outages) > 0}
    except Exception:
        return {"ioda_outages": 0, "ioda_confirmed": False}


# ─── Status logic ─────────────────────────────────────────────────────────────

def compute_status(current: dict, previous: dict) -> tuple[str, str]:
    """
    Returns (status, status_since).
    GREEN  = up ≥ STABLE_THRESHOLD for > STABLE_HOURS
    YELLOW = up ≥ STABLE_THRESHOLD but only recently recovered
    RED    = down or severely degraded
    """
    pct       = current["visibility_pct"]
    announced = current["announced"]
    now_iso   = current["timestamp"]
    now       = datetime.fromisoformat(now_iso)

    prev_status = previous.get("status", "RED")
    prev_since  = previous.get("status_since", now_iso)

    if not announced or pct < OUTAGE_THRESHOLD:
        # Network is down
        if prev_status == "RED":
            return "RED", prev_since        # already red — keep since
        return "RED", now_iso               # newly red

    # Network looks up (pct ≥ OUTAGE_THRESHOLD)
    if pct < STABLE_THRESHOLD:
        # Degraded but not fully down — treat as YELLOW
        if prev_status in ("YELLOW", "GREEN"):
            return "YELLOW", prev_since
        return "YELLOW", now_iso

    # pct ≥ STABLE_THRESHOLD
    if prev_status == "RED":
        # Just recovered — start YELLOW timer
        return "YELLOW", now_iso

    if prev_status == "YELLOW":
        since = datetime.fromisoformat(prev_since)
        if (now - since).total_seconds() / 3600 >= STABLE_HOURS:
            return "GREEN", prev_since      # promoted to stable
        return "YELLOW", prev_since

    # Was GREEN, stays GREEN
    return "GREEN", prev_since


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


# ─── Outage event handling ─────────────────────────────────────────────────────

async def handle_status_change(asn: str, name: str, prev_status: str,
                                curr_status: str, curr: dict, outages: list):
    if prev_status == curr_status:
        return outages

    now     = datetime.now(timezone.utc)
    vis_pct = int(curr["visibility_pct"] * 100)
    vis_str = (f"{vis_pct}% visible "
               f"({curr['visible_collectors']}/{curr['total_collectors']} peers)")

    if curr_status == "RED" and prev_status in ("GREEN", "YELLOW", "UNKNOWN"):
        await send_alert(
            f"🔴 *BGP ALERT — DOWN*\n\n"
            f"*{name}* ({asn})\n"
            f"Visibility: {vis_str}\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Possible internet shutdown. IODA cross-check pending.\n"
            f"Reply /draft to start an article."
        )
        outages.append({
            "asn": asn, "name": name, "status": "DOWN",
            "started_at": now.isoformat(), "ended_at": None,
            "duration_minutes": None,
            "min_visibility_pct": curr["visibility_pct"],
            "ioda_confirmed": False, "resolved": False,
        })

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
                h, m = divmod(duration_min, 60)
                dur = f"{h}h {m}min" if h else f"{m}min"
                await send_alert(
                    f"🟡 *BGP RECOVERY — monitoring*\n\n"
                    f"*{name}* ({asn}) is back online.\n"
                    f"Outage duration: *{dur}*\n"
                    f"Visibility: {vis_str}\n"
                    f"Monitoring for 1h before marking stable."
                )
                break

    elif curr_status == "GREEN" and prev_status == "YELLOW":
        await send_alert(
            f"✅ *BGP STABLE*\n\n"
            f"*{name}* ({asn}) stable for 1h+.\n"
            f"Visibility: {vis_str}"
        )

    return outages


# ─── History ──────────────────────────────────────────────────────────────────

def update_history(current_statuses: dict):
    history = load_json(HISTORY_FILE, [])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    history = [h for h in history if h["timestamp"] > cutoff]
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "statuses": {
            asn: {"status": s["status"], "visibility_pct": s["visibility_pct"]}
            for asn, s in current_statuses.items()
        }
    })
    save_json(HISTORY_FILE, history)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def check_asns(asn_list: list[dict], test_mode: bool = False):
    previous  = load_json(ASN_STATUS_FILE, {})
    outages   = load_json(OUTAGES_FILE, [])
    current_statuses = {}

    headers = {"User-Agent": "IIM-BGP-Monitor/1.0 (+https://internetinmyanmar.com)"}

    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [get_routing_status(a["asn"], a["name"], client) for a in asn_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for entry, result in zip(asn_list, results):
            asn = entry["asn"]
            if isinstance(result, Exception):
                log.warning("Error checking %s: %s", asn, result)
                continue

            prev = previous.get(asn, {})
            prev_status = prev.get("status", "UNKNOWN")

            status, status_since = compute_status(result, prev)
            result["status"]       = status
            result["status_since"] = status_since

            if test_mode:
                print(f"{asn:12} {result['name'][:40]:40} "
                      f"{status:6} {int(result['visibility_pct']*100):3}%")
                continue

            current_statuses[asn] = result

            outages = await handle_status_change(
                asn, result["name"], prev_status, status, result, outages
            )

            # IODA cross-check for critical ASNs that just went RED
            if status == "RED" and asn in CRITICAL_ASNS and prev_status != "RED":
                ioda = await get_ioda_status(asn, client)
                result.update(ioda)
                for outage in reversed(outages):
                    if outage["asn"] == asn and not outage["resolved"]:
                        outage["ioda_confirmed"] = ioda["ioda_confirmed"]
                        break

    if test_mode:
        return

    # Merge with previous (preserve ASNs not checked this run)
    merged = {**previous, **current_statuses}
    save_json(ASN_STATUS_FILE, merged)
    save_json(OUTAGES_FILE, outages)
    update_history(current_statuses)

    down     = [s for s in current_statuses.values() if s["status"] == "RED"]
    yellow   = [s for s in current_statuses.values() if s["status"] == "YELLOW"]
    checked  = len(current_statuses)

    if down:
        log.warning("RED (%d/%d): %s", len(down), checked,
                    [s["asn"] for s in down])
    if yellow:
        log.info("YELLOW (%d/%d): %s", len(yellow), checked,
                 [s["asn"] for s in yellow])
    if not down and not yellow:
        log.info("All %d ASNs GREEN", checked)


async def run(args):
    headers = {"User-Agent": "IIM-BGP-Monitor/1.0 (+https://internetinmyanmar.com)"}

    if args.test:
        # Test mode: check the 5 critical ASNs, print, exit
        print("BGP monitor test — checking critical ASNs\n")
        test_list = [{"asn": a, "name": a} for a in sorted(CRITICAL_ASNS)]
        await check_asns(test_list, test_mode=True)
        return

    async with httpx.AsyncClient(headers=headers) as client:
        all_asns = await fetch_routed_asns(client)

    if args.critical_only:
        asn_list = [a for a in all_asns if a["asn"] in CRITICAL_ASNS]
        log.info("Critical-only mode: %d ASNs", len(asn_list))
    else:
        asn_list = all_asns
        log.info("Full run: %d routed MM ASNs", len(asn_list))

    await check_asns(asn_list)

    # Push updated JSON to git so Cloudflare rebuilds the frontend
    _git_push_data()


def _git_push_data():
    """Commit and push updated BGP JSON files to git."""
    import subprocess
    repo = Path(__file__).parent.parent  # ~/agents/../ = repo root
    files = [
        str(ASN_STATUS_FILE.resolve()),
        str(OUTAGES_FILE.resolve()),
        str(HISTORY_FILE.resolve()),
    ]
    try:
        subprocess.run(["git", "-C", str(repo), "add"] + files, check=True)
        result = subprocess.run(
            ["git", "-C", str(repo), "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if result.returncode == 0:
            log.info("BGP data unchanged — no git commit needed")
            return
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m",
             f"data: BGP status update {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"],
            check=True
        )
        subprocess.run(["git", "-C", str(repo), "push"], check=True)
        log.info("BGP data pushed to git")
    except Exception as e:
        log.error("git push failed: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGP monitor for Myanmar ASNs")
    parser.add_argument("--critical-only", action="store_true",
                        help="Check only the 5 critical ASNs (fast, for 5-min cron)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: check critical ASNs, print results, no file writes")
    args = parser.parse_args()
    asyncio.run(run(args))
