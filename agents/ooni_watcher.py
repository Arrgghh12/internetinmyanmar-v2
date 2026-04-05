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

load_dotenv()
log = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent
CONFIG = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())

OONI_API = "https://api.ooni.io/api/v1"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME = CONFIG["github"]["repo"]


# ---------------------------------------------------------------------------
# OONI data fetching
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_recent_measurements(limit: int = 200) -> list[dict]:
    resp = requests.get(
        f"{OONI_API}/measurements",
        params={"probe_cc": "MM", "limit": limit, "order_by": "test_start_time"},
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
def fetch_network_outages() -> dict:
    """Fetch OONI network outage data for Myanmar."""
    resp = requests.get(
        f"{OONI_API}/observations",
        params={"probe_cc": "MM", "limit": 50},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


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

def push_to_github(stats: dict):
    """Update observatory/stats.json in the repo to trigger a Cloudflare rebuild."""
    if not GITHUB_TOKEN:
        log.warning("No GITHUB_TOKEN — skipping GitHub push")
        return

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    path = "src/content/observatory/stats.json"
    content = json.dumps(stats, indent=2, ensure_ascii=False)

    try:
        existing = repo.get_contents(path, ref="main")
        repo.update_file(
            path,
            f"observatory: update stats {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
            content,
            existing.sha,
            branch="main",
        )
        log.info("Pushed updated stats.json to GitHub (main)")
    except Exception as e:
        log.error(f"GitHub push failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(test: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log.info("=== OONI Watcher starting ===")

    measurements = fetch_recent_measurements()
    log.info(f"Fetched {len(measurements)} measurements")

    blocked = fetch_blocked_sites()
    log.info(f"Fetched {len(blocked)} confirmed blocked entries")

    stats = compute_stats(measurements, blocked)
    log.info(f"Stats: {json.dumps(stats)}")

    # Write locally too (for VPS-side reference)
    local_path = AGENTS_DIR / "observatory_stats.json"
    local_path.write_text(json.dumps(stats, indent=2))

    if test:
        log.info("--test mode: skipping GitHub push")
        print(json.dumps(stats, indent=2))
        return

    push_to_github(stats)
    log.info("=== OONI Watcher done ===")


if __name__ == "__main__":
    run(test="--test" in sys.argv)
