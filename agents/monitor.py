"""
Monitor
-------
Fetches all configured RSS/API sources, scores each item via Claude,
saves results to monitor_output.json, then triggers brief_generator.py
for items above the score threshold.

Runs daily at 6:30 AM via cron:
  30 6 * * * ~/agents/venv/bin/python ~/agents/monitor.py >> ~/logs/monitor.log 2>&1

Usage:
  python monitor.py              # full run
  python monitor.py --dry-run    # fetch + score, skip brief generation
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import anthropic
import feedparser
import httpx
import yaml
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

import requests

load_dotenv()
log = logging.getLogger(__name__)


def _notify_telegram(text: str) -> None:
    """Send a plain text message to Anna's Telegram chat."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping notification")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram notify failed: {e}")

AGENTS_DIR = Path(__file__).parent
CONFIG = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())
CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
VENV_PYTHON = AGENTS_DIR / "venv" / "bin" / "python"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

async def fetch_feed(name: str, url: str, client: httpx.AsyncClient) -> list[dict]:
    """Fetch an RSS feed and return normalised items."""
    try:
        resp = await client.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        items = []
        for entry in feed.entries[:20]:  # cap per source
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            items.append({
                "source": name,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", "")[:500],
                "published": datetime(*published[:6], tzinfo=timezone.utc).isoformat()
                if published else None,
            })
        log.info(f"{name}: {len(items)} items")
        return items
    except Exception as e:
        log.warning(f"{name}: fetch failed — {e}")
        return []


async def fetch_ooni(client: httpx.AsyncClient) -> list[dict]:
    """Fetch recent OONI anomalies for Myanmar."""
    try:
        ooni_url = CONFIG["sources"]["tier1"]["ooni_api"]["url"]
        resp = await client.get(
            ooni_url,
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for m in data.get("results", [])[:20]:
            if m.get("anomaly"):
                items.append({
                    "source": "ooni",
                    "title": f"OONI anomaly: {m.get('input', 'unknown')} on {m.get('probe_asn', '')}",
                    "url": f"https://explorer.ooni.org/measurement/{m.get('report_id', '')}",
                    "summary": f"Test: {m.get('test_name')} | ASN: {m.get('probe_asn')} | "
                               f"Confirmed blocked: {m.get('confirmed')}",
                    "published": m.get("measurement_start_time"),
                })
        log.info(f"ooni: {len(items)} anomalies")
        return items
    except Exception as e:
        log.warning(f"ooni: fetch failed — {e}")
        return []


def _rss_sources() -> list[tuple[str, str]]:
    """Flatten the nested sources config into (name, url) pairs for RSS feeds."""
    pairs = []
    for tier_key, tier_val in CONFIG["sources"].items():
        if not isinstance(tier_val, dict):
            continue
        for src_name, src_cfg in tier_val.items():
            if not isinstance(src_cfg, dict):
                continue
            url = src_cfg.get("url", "")
            fetch_type = src_cfg.get("type", "rss")
            fetch_method = src_cfg.get("fetch", "rss")
            # Only auto-fetch RSS/API types (skip manual/tavily/scrape)
            if fetch_type in ("rss",) and fetch_method not in ("manual", "tavily", "scrape"):
                pairs.append((f"{tier_key}:{src_name}", url))
    return pairs


async def fetch_all() -> list[dict]:
    """Fetch all sources concurrently."""
    rss_pairs = _rss_sources()
    async with httpx.AsyncClient(headers={"User-Agent": "IIMBot/1.0"}) as client:
        tasks = [fetch_feed(name, url, client) for name, url in rss_pairs]
        tasks.append(fetch_ooni(client))
        results = await asyncio.gather(*tasks)
    items = [item for batch in results for item in batch]
    log.info(f"Total items fetched: {len(items)}")
    return items


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

SCORE_PROMPT = """Score this news item for relevance to Myanmar internet freedom,
censorship, shutdowns, and digital rights.

Return JSON only:
{
  "score": <float 0-10>,
  "reason": "<one sentence>",
  "tags": ["tag1", "tag2"],
  "category": "<one of: Censorship & Shutdowns | Telecom & Infrastructure | Digital Economy | Guides & Tools | News - Mobile | News - Broadband | News - Policy>"
}

Scoring criteria:
- 40% relevance to Myanmar internet freedom / censorship / digital rights
- 25% relevance to telecom / connectivity infrastructure
- 20% quality: substantive, has a clear news angle
- 15% not outdated / fits the monitoring mission

Low score (<4): crypto, travel, unrelated Myanmar news, too vague."""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def score_item(item: dict) -> dict:
    text = f"Title: {item['title']}\nSource: {item['source']}\nSummary: {item['summary']}"
    response = CLIENT.messages.create(
        model=CONFIG["anthropic"]["models"]["score"],
        max_tokens=CONFIG["anthropic"]["max_tokens"]["score"],
        system="Respond with JSON only. No preamble.",
        messages=[{"role": "user", "content": f"{SCORE_PROMPT}\n\nItem:\n{text}"}],
    )
    scored = json.loads(response.content[0].text)
    return {**item, **scored}


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove near-duplicate titles."""
    seen, out = set(), []
    for item in items:
        key = item["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    log.info("=== Monitor starting ===")
    items = asyncio.run(fetch_all())
    items = deduplicate(items)
    log.info(f"After dedup: {len(items)} items")

    scored = []
    for item in items:
        try:
            scored.append(score_item(item))
        except Exception as e:
            log.warning(f"Scoring failed for '{item['title'][:50]}': {e}")

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    output_path = AGENTS_DIR / "monitor_output.json"
    output_path.write_text(json.dumps(scored, indent=2, ensure_ascii=False))
    log.info(f"Saved {len(scored)} scored items to {output_path}")

    above_threshold = [s for s in scored if s.get("score", 0) >= CONFIG["scoring"]["min_score_for_brief"]]
    log.info(f"{len(above_threshold)} items above threshold {CONFIG['scoring']['min_score_for_brief']}")

    if dry_run:
        log.info("Dry run — skipping brief generation")
        for item in above_threshold[:5]:
            log.info(f"  [{item.get('score', 0):.1f}] {item['title'][:70]}")
        return

    if above_threshold:
        log.info("Triggering brief_generator.py…")
        result = subprocess.run(
            [str(VENV_PYTHON), str(AGENTS_DIR / "brief_generator.py")],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            log.error(f"brief_generator.py failed:\n{result.stderr}")
        else:
            log.info("brief_generator.py completed")
    else:
        msg = CONFIG.get("scoring", {}).get("no_news_message", "No noteworthy news today — no brief generated.")
        log.info(msg)
        _notify_telegram(msg)

    log.info("=== Monitor done ===")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
