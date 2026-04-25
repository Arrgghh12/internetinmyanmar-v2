"""
KeepItOn Fetcher
----------------
Downloads the Access Now STOP dataset (verified internet shutdowns),
filters to Myanmar, and publishes keepiton-shutdowns.json to the repo.

Runs weekly via cron (Sundays 9 AM):
  0 9 * * 0 ~/agents/venv/bin/python ~/agents/keepiton_fetcher.py >> ~/logs/keepiton.log 2>&1

Usage:
  python keepiton_fetcher.py           # full run
  python keepiton_fetcher.py --dry-run # fetch + parse only, no GitHub push
"""

import csv
import io
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

AGENTS_DIR   = Path(__file__).parent
CONFIG       = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_NAME    = CONFIG["github"]["repo"]

KIT_CFG      = CONFIG.get("keepiton", {})
SHEET_URL    = KIT_CFG.get("sheet_url", "")
COUNTRY      = KIT_CFG.get("country_filter", "Myanmar")
OUTPUT_PATH  = KIT_CFG.get("output_path", "src/data/keepiton-shutdowns.json")

PLATFORM_COLS = [
    "facebook_affected", "twitter_affected", "whatsapp_affected",
    "instagram_affected", "telegram_affected", "other_affected",
]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_csv() -> list[dict]:
    if not SHEET_URL:
        raise ValueError("keepiton.sheet_url not set in config.yaml")
    resp = requests.get(SHEET_URL, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")))
    rows = list(reader)
    log.info("Downloaded %d rows from STOP dataset", len(rows))
    return rows


# ---------------------------------------------------------------------------
# Normalise
# ---------------------------------------------------------------------------

def normalize_date(raw: str) -> str | None:
    """Parse various date formats to YYYY-MM-DD, or None if unparseable."""
    raw = (raw or "").strip()
    if not raw or raw.lower() in ("ongoing", "n/a", "unknown", "tbd", "present"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try partial: "2021-02" → treat as first of month
    if len(raw) == 7 and raw[4] == "-":
        return raw + "-01"
    log.debug("Could not parse date: %r", raw)
    return None


def classify_type(row: dict) -> str:
    """Classify shutdown type from STOP dataset fields."""
    extent = (row.get("shutdown_extent") or "").lower()
    stype  = (row.get("shutdown_type") or "").lower()
    net    = (row.get("affected_network") or "").lower()

    if "full" in extent:
        return "full_network"
    if "throttl" in stype or "throttl" in extent or "slow" in stype:
        return "throttle"
    active_platforms = [c for c in PLATFORM_COLS if str(row.get(c, "")).strip().lower() == "yes"]
    if active_platforms and "broadband" not in net and "fixed" not in net:
        return "platform"
    if "mobile" in net or "mobile" in stype:
        return "mobile"
    return "full_network"


def parse_services(row: dict) -> list[str]:
    services = []
    net = (row.get("affected_network") or "").strip()
    if net:
        services.extend([s.strip() for s in net.split(",") if s.strip()])
    for col in PLATFORM_COLS:
        if str(row.get(col, "")).strip().lower() == "yes":
            name = col.replace("_affected", "").replace("_", " ").title()
            services.append(name)
    return list(dict.fromkeys(services))[:6]  # dedupe + cap


def normalise_row(row: dict) -> dict | None:
    """Return a clean event dict or None if the row should be skipped."""
    # Country filter — try multiple possible column names
    country_val = (
        row.get("country") or row.get("Country") or
        row.get("country_name") or ""
    ).strip()
    if COUNTRY.lower() not in country_val.lower():
        return None

    start = normalize_date(row.get("start_date") or row.get("Start date") or "")
    if not start:
        return None  # events without a start date are unusable

    status  = (row.get("shutdown_status") or "").strip().lower()
    end_raw = (row.get("end_date") or "").strip()
    ongoing = status in ("ongoing", "") or end_raw.lower() in ("ongoing", "", "present", "n/a", "tbd")
    end     = None if ongoing else normalize_date(end_raw)

    # Prefer area_name (specific) over geo_scope (verbose description)
    area  = (row.get("area_name") or "").strip()
    scope = area if area else (row.get("geo_scope") or "Myanmar").strip()

    # First URL from semicolon-separated info_source_link, fallback to an_link
    raw_urls  = (row.get("info_source_link") or row.get("an_link") or "").strip()
    source_url = raw_urls.split(";")[0].strip() if raw_urls else ""

    return {
        "id":          (row.get("id") or "").strip(),
        "startDate":   start,
        "endDate":     end,
        "ongoing":     ongoing,
        "type":        classify_type(row),
        "scope":       scope,
        "perpetrator": (row.get("ordered_by") or row.get("decision_maker") or "").strip(),
        "services":    parse_services(row),
        "sourceUrl":   source_url,
    }


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def push_to_github(payload: dict) -> None:
    if not GITHUB_TOKEN:
        log.warning("No GITHUB_TOKEN — skipping GitHub push")
        return
    g    = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    try:
        existing = repo.get_contents(OUTPUT_PATH, ref="main")
        repo.update_file(
            OUTPUT_PATH,
            f"keepiton: update keepiton-shutdowns.json {ts} UTC",
            content,
            existing.sha,
            branch="main",
        )
    except Exception:
        repo.create_file(
            OUTPUT_PATH,
            f"keepiton: create keepiton-shutdowns.json {ts} UTC",
            content,
            branch="main",
        )
    log.info("Pushed %s to GitHub (main)", OUTPUT_PATH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("=== KeepItOn Fetcher starting (dry_run=%s) ===", dry_run)

    rows = fetch_csv()
    events = []
    for row in rows:
        event = normalise_row(row)
        if event:
            events.append(event)

    events.sort(key=lambda e: e["startDate"])
    log.info("Found %d Myanmar events from %d total rows", len(events), len(rows))

    payload = {
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totalEvents": len(events),
        "source":      "Access Now STOP Dataset · accessnow.org/keepiton",
        "events":      events,
    }

    if dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        log.info("Dry run — not pushing to GitHub")
        return

    push_to_github(payload)
    log.info("=== KeepItOn Fetcher done ===")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
