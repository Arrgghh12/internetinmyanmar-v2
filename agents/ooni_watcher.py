"""
OONI Watcher
------------
Fetches OONI measurement data for Myanmar and updates the Observatory
JSON files used by the live stats strip on the homepage.

Runs twice daily via cron:
  0 8,20 * * * ~/agents/venv/bin/python ~/agents/ooni_watcher.py >> ~/logs/ooni.log 2>&1

Also pushes updated JSON to GitHub so Cloudflare rebuilds with fresh data.

Usage:
  python ooni_watcher.py          # full run
  python ooni_watcher.py --test   # fetch only, no GitHub push
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from github import Github
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent
CONFIG = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())

OONI_API       = "https://api.ooni.io/api/v1"
CF_RADAR_API      = "https://api.cloudflare.com/client/v4/radar"
CF_RADAR_NETFLOWS = f"{CF_RADAR_API}/netflows/timeseries"
CF_RADAR_TOKEN    = os.environ.get("CF_RADAR_API_TOKEN", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME      = CONFIG["github"]["repo"]


# ---------------------------------------------------------------------------
# OONI data fetching
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_recent_measurements(limit: int = 200) -> list[dict]:
    resp = requests.get(
        f"{OONI_API}/measurements",
        params={"probe_cc": "MM", "limit": limit},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_blocked_sites(limit: int = 500) -> list[dict]:
    """Fetch confirmed blocked URLs in Myanmar."""
    resp = requests.get(
        f"{OONI_API}/measurements",
        params={
            "probe_cc": "MM",
            "confirmed": "true",
            "test_name": "web_connectivity",
            "limit": limit,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_ooni_history(time_grain: str, since: str) -> list[dict]:
    """Fetch aggregated OONI measurements for Myanmar at any time granularity."""
    resp = requests.get(
        f"{OONI_API}/aggregation",
        params={
            "probe_cc": "MM",
            "test_name": "web_connectivity",
            "since": since,
            "time_grain": time_grain,
            "axis_x": "measurement_start_day",
        },
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json().get("result", [])
    for row in result:
        total   = row.get("measurement_count", 0)
        anomaly = row.get("anomaly_count", 0)
        row["anomaly_rate"] = round(anomaly / total * 100, 1) if total > 0 else 0
        row["period"] = row.get("measurement_start_day", "")[:10]
        # Keep legacy "month" key on monthly rows so existing templates don't break
        if time_grain == "month":
            row["month"] = row["period"][:7]
    return sorted(result, key=lambda x: x["period"])


# ---------------------------------------------------------------------------
# Cloudflare Radar — netflows (traffic volume)
# ---------------------------------------------------------------------------

def _fetch_cf_netflow_series(date_range: str, agg_interval: str) -> list[dict]:
    """Fetch a single CF Radar netflows timeseries, normalised 0–100."""
    if not CF_RADAR_TOKEN:
        return []
    try:
        resp = requests.get(
            CF_RADAR_NETFLOWS,
            params={"location": "MM", "dateRange": date_range,
                    "aggInterval": agg_interval, "format": "json"},
            headers={"Authorization": f"Bearer {CF_RADAR_TOKEN}"},
            timeout=20,
        )
        resp.raise_for_status()
        result     = resp.json().get("result", {})
        # CF Radar netflows: {"serie_0": {"timestamps": [...], "values": ["1.0","0.97",...]}, "meta": ...}
        # Values are already normalised strings in the 0–1 range (1.0 = peak)
        serie      = result.get("serie_0", {})
        timestamps = serie.get("timestamps", [])
        values_raw = serie.get("values", [])
        if not timestamps or not values_raw:
            log.warning("CF netflows (%s/%s): empty serie_0", date_range, agg_interval)
            return []
        return [
            {"timestamp": ts, "cf_traffic": round(float(v) * 100, 1)}
            for ts, v in zip(timestamps, values_raw)
        ]
    except Exception as e:
        log.warning("CF netflows fetch failed (%s/%s): %s", date_range, agg_interval, e)
        return []


def fetch_cf_traffic_all_scales() -> dict:
    """Fetch CF Radar traffic for all three chart scales (monthly, weekly, daily)."""
    now = datetime.now(timezone.utc)
    weekly_raw = _fetch_cf_netflow_series("52w", "1w")

    # Bucket weekly points into calendar months for the 5-year overlay
    monthly_by_month: dict[str, list[float]] = {}
    for pt in weekly_raw:
        m = pt["timestamp"][:7]   # "YYYY-MM"
        monthly_by_month.setdefault(m, []).append(pt["cf_traffic"])
    monthly = [
        {"month": m, "cf_traffic": round(sum(v) / len(v), 1)}
        for m, v in sorted(monthly_by_month.items())
    ]

    daily_raw = _fetch_cf_netflow_series("28d", "1d")

    log.info(
        "CF traffic fetched: monthly=%d months, weekly=%d pts, daily=%d pts",
        len(monthly), len(weekly_raw), len(daily_raw),
    )
    return {
        "lastUpdated": now.isoformat(),
        "monthly": monthly,
        "weekly":  weekly_raw,
        "daily":   daily_raw,
    }


def _fetch_existing_json(repo_path: str):
    """Fetch a JSON file from GitHub. Returns parsed content or None on failure."""
    if not GITHUB_TOKEN:
        return None
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        f = repo.get_contents(repo_path, ref="main")
        return json.loads(f.decoded_content)
    except Exception as e:
        log.warning("Could not fetch %s for merge: %s", repo_path, e)
        return None


def _merge_by_key(existing: list[dict], new: list[dict], key: str) -> list[dict]:
    """Merge two lists of dicts, new wins on key collision, sorted by key."""
    new_keys = {p[key] for p in new}
    merged = [p for p in existing if p.get(key) not in new_keys] + new
    return sorted(merged, key=lambda x: x.get(key, ""))


def fetch_cf_radar_outages() -> dict:
    """
    Fetch outage annotations for Myanmar (MM) from Cloudflare Radar.
    Returns a dict ready to write to cf-radar-outages.json.
    Gracefully returns empty data if CF_RADAR_API_TOKEN is not configured.
    """
    now = datetime.now(timezone.utc)
    empty = {"lastUpdated": now.isoformat(), "activeOutages": [], "recentOutages": []}

    if not CF_RADAR_TOKEN:
        log.warning("CF_RADAR_API_TOKEN not set — skipping Cloudflare Radar fetch")
        return empty

    try:
        resp = requests.get(
            f"{CF_RADAR_API}/annotations/outages",
            params={"location": "MM", "dateRange": "7d", "limit": 20},
            headers={"Authorization": f"Bearer {CF_RADAR_TOKEN}"},
            timeout=15,
        )
        resp.raise_for_status()
        annotations = resp.json().get("result", {}).get("annotations", [])
    except Exception as e:
        log.error("Cloudflare Radar fetch failed: %s", e)
        return empty

    active: list[dict] = []
    recent: list[dict] = []

    for ann in annotations:
        end   = ann.get("end_date") or ann.get("endDate")
        start = ann.get("start_date") or ann.get("startDate") or ann.get("start", "")

        normalized = {
            "id":          ann.get("id", ""),
            "start":       start,
            "end":         end,
            "asns":        ann.get("asns", []),
            "locations":   ann.get("locations", ["MM"]),
            "description": ann.get("description", ""),
            "eventTags":   ann.get("event_tags") or ann.get("eventTags") or [],
            "linkedUrl":   ann.get("linked_url") or ann.get("linkedUrl") or "",
            "scope":       ann.get("scope", ""),
        }

        # Active = no end date, or end date is still in the future
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
        except Exception:
            end_dt = None

        if end_dt is None or end_dt > now:
            active.append(normalized)
        else:
            recent.append(normalized)

    return {
        "lastUpdated":   now.isoformat(),
        "activeOutages": active,
        "recentOutages": recent[:5],
    }


def compute_stats(measurements: list[dict], blocked: list[dict]) -> dict:
    """Derive Observatory stats from raw OONI data."""
    now = datetime.now(timezone.utc)

    # Count anomalies in last 24h as proxy for active shutdowns
    recent_anomalies = [
        m for m in measurements
        if m.get("anomaly") and m.get("measurement_start_time", "")[:10] == now.date().isoformat()
    ]

    # Unique blocked domains
    blocked_domains = set()
    for m in blocked:
        url = m.get("input", "")
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                if domain:
                    blocked_domains.add(domain)
            except Exception:
                pass

    # Estimate active shutdowns from anomaly density
    # Cluster anomalies by ASN — each ASN with >3 anomalies today = likely shutdown
    asn_anomalies: dict[str, int] = {}
    for m in recent_anomalies:
        asn = m.get("probe_asn", "unknown")
        asn_anomalies[asn] = asn_anomalies.get(asn, 0) + 1
    active_shutdowns = sum(1 for count in asn_anomalies.values() if count >= 3)

    # Days since last major outage (>10 anomalies in a single day)
    daily_counts: dict[str, int] = {}
    for m in measurements:
        if m.get("anomaly"):
            day = m.get("measurement_start_time", "")[:10]
            if day:
                daily_counts[day] = daily_counts.get(day, 0) + 1

    days_since_major = 0
    for i, day in enumerate(sorted(daily_counts.keys(), reverse=True)):
        if daily_counts[day] >= 10:
            days_since_major = i
            break

    return {
        "lastUpdated": now.isoformat(),
        "activeShutdowns": active_shutdowns,
        "blockedSites": len(blocked_domains),
        "daysSinceLastMajorOutage": days_since_major,
        "rawAnomaliesLast24h": len(recent_anomalies),
        "totalMeasurementsScanned": len(measurements),
    }


# ---------------------------------------------------------------------------
# GitHub push
# ---------------------------------------------------------------------------

def push_to_github(
    stats: dict,
    history: list[dict] | None = None,
    cf_outages: dict | None = None,
    ooni_weekly: list[dict] | None = None,
    ooni_daily: list[dict] | None = None,
    cf_traffic: dict | None = None,
):
    """Update observatory/stats.json in the repo to trigger a Cloudflare rebuild."""
    if not GITHUB_TOKEN:
        log.warning("No GITHUB_TOKEN — skipping GitHub push")
        return

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')

    files_to_update = {
        "src/content/observatory/stats.json": json.dumps(stats, indent=2),
    }
    if history:
        files_to_update["src/data/ooni-history.json"] = json.dumps(history, indent=2)
    if cf_outages:
        files_to_update["src/data/cf-radar-outages.json"] = json.dumps(cf_outages, indent=2)
    if ooni_weekly is not None:
        files_to_update["src/data/ooni-history-weekly.json"] = json.dumps(ooni_weekly, indent=2)
    if ooni_daily is not None:
        files_to_update["src/data/ooni-history-daily.json"] = json.dumps(ooni_daily, indent=2)
    if cf_traffic is not None:
        files_to_update["src/data/cf-traffic.json"] = json.dumps(cf_traffic, indent=2)

    # Update lastUpdated in blocked-sites.json without touching the curated domain list
    try:
        blocked_sites_path = "src/data/blocked-sites.json"
        existing_blocked = repo.get_contents(blocked_sites_path, ref="main")
        blocked_data = json.loads(existing_blocked.decoded_content)
        blocked_data["lastUpdated"] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        files_to_update[blocked_sites_path] = json.dumps(blocked_data, indent=2)
    except Exception as e:
        log.warning(f"Could not update blocked-sites.json lastUpdated: {e}")

    for path, content in files_to_update.items():
        try:
            try:
                existing = repo.get_contents(path, ref="main")
                repo.update_file(
                    path,
                    f"observatory: update {path.split('/')[-1]} {timestamp} UTC",
                    content,
                    existing.sha,
                    branch="main",
                )
            except Exception:
                repo.create_file(
                    path,
                    f"observatory: create {path.split('/')[-1]} {timestamp} UTC",
                    content,
                    branch="main",
                )
            log.info(f"Pushed {path} to GitHub (main)")
        except Exception as e:
            log.error(f"GitHub push failed for {path}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(test: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log.info("=== OONI Watcher starting ===")

    from datetime import timedelta

    measurements = fetch_recent_measurements()
    log.info(f"Fetched {len(measurements)} measurements")

    blocked = fetch_blocked_sites()
    log.info(f"Fetched {len(blocked)} confirmed blocked entries")

    now_utc = datetime.now(timezone.utc)
    since_daily = (now_utc - timedelta(days=28)).strftime("%Y-%m-%d")

    history = fetch_ooni_history("month", "2021-02-01")
    log.info(f"Fetched {len(history)} months of historical data")

    # Fetch full weekly history from coup start — OONI stores it all
    ooni_weekly = fetch_ooni_history("week", "2021-02-01")
    log.info(f"Fetched {len(ooni_weekly)} weeks of OONI data")

    ooni_daily = fetch_ooni_history("day", since_daily)
    log.info(f"Fetched {len(ooni_daily)} days of OONI data")

    cf_outages = fetch_cf_radar_outages()
    log.info(f"Cloudflare Radar: {len(cf_outages['activeOutages'])} active outage(s) for MM")

    cf_traffic = fetch_cf_traffic_all_scales()

    # Merge all rolling-window data with existing files so nothing is ever lost.
    # CF Radar API returns at most 12 months back; OONI daily fetches only 28 days.
    # Without merging, data older than the API window would be silently dropped each run.
    if not test:
        existing_cf = _fetch_existing_json("src/data/cf-traffic.json") or {}
        for scale, key in (("monthly", "month"), ("weekly", "timestamp"), ("daily", "timestamp")):
            if existing_cf.get(scale):
                cf_traffic[scale] = _merge_by_key(existing_cf[scale], cf_traffic[scale], key)
                log.info("CF %s merged: %d points total", scale, len(cf_traffic[scale]))

        existing_daily = _fetch_existing_json("src/data/ooni-history-daily.json") or []
        if existing_daily:
            ooni_daily = _merge_by_key(existing_daily, ooni_daily, "period")
            log.info("OONI daily merged: %d days total", len(ooni_daily))

    stats = compute_stats(measurements, blocked)
    log.info(f"Stats: {json.dumps(stats)}")

    # Write locally too (for VPS-side reference)
    local_path = AGENTS_DIR / "observatory_stats.json"
    local_path.write_text(json.dumps(stats, indent=2))

    if test:
        log.info("--test mode: skipping GitHub push")
        print(json.dumps(stats, indent=2))
        print(f"\nHistory sample ({len(history)} months):")
        for row in history[-3:]:
            print(f"  {row['month']}: {row['anomaly_count']} anomalies / {row['measurement_count']} total ({row['anomaly_rate']}%)")
        print(f"\nOONI weekly: {len(ooni_weekly)} rows, daily: {len(ooni_daily)} rows")
        print(f"CF traffic: monthly={len(cf_traffic['monthly'])}, weekly={len(cf_traffic['weekly'])}, daily={len(cf_traffic['daily'])}")
        print(f"CF outages: {json.dumps(cf_outages, indent=2)}")
        return

    push_to_github(stats, history, cf_outages, ooni_weekly, ooni_daily, cf_traffic)
    log.info("=== OONI Watcher done ===")


if __name__ == "__main__":
    run(test="--test" in sys.argv)
