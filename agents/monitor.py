"""
Monitor
-------
Fetches all RSS feeds from feeds.yaml, keeps only entries published in the
last 24 h, scores each for relevance to Myanmar internet freedom, and sends
a Telegram digest for items that pass the threshold.

Runs daily at 6:30 AM via cron:
  30 6 * * * ~/agents/venv/bin/python ~/agents/monitor.py >> ~/logs/monitor.log 2>&1

Usage:
  python monitor.py              # full run
  python monitor.py --dry-run    # fetch + score, skip Telegram
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import requests
import yaml
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from urllib.parse import quote

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)

AGENTS_DIR  = Path(__file__).parent
CONFIG      = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())
FEEDS       = yaml.safe_load((AGENTS_DIR / "feeds.yaml").read_text())["feeds"]
OUTPUT_PATH = AGENTS_DIR / "monitor_output.json"

CLIENT: OpenAI | None = None  # initialised in run()

MAX_AGE_HOURS   = int(os.getenv("MONITOR_MAX_AGE_HOURS", "24"))
MIN_SCORE       = float(CONFIG.get("scoring", {}).get("min_score_for_brief", 6.0))
MAX_ITEMS_PER_FEED = 20   # cap per feed to avoid runaway costs


def gt_url(url: str) -> str:
    return f"https://translate.google.com/translate?sl=my&tl=en&u={quote(url, safe='')}"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

async def fetch_feed(feed_cfg: dict, client: httpx.AsyncClient,
                     cutoff: datetime) -> list[dict]:
    key = feed_cfg["key"]
    url = feed_cfg["url"]
    lang = feed_cfg.get("lang", "en")
    keyword_filter = feed_cfg.get("filter", "").lower()

    try:
        resp = await client.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        items = []
        for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc) if published else None

            # Drop entries older than cutoff
            if pub_dt and pub_dt < cutoff:
                continue

            title   = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()[:500]

            # Apply keyword filter if configured (e.g. access_now → filter: myanmar)
            if keyword_filter:
                combined = (title + " " + summary).lower()
                if keyword_filter not in combined:
                    continue

            items.append({
                "source":    key,
                "lang":      lang,
                "title":     title,
                "url":       entry.get("link", ""),
                "summary":   summary,
                "published": pub_dt.isoformat() if pub_dt else None,
            })
        log.info(f"{key}: {len(items)} fresh items")
        return items
    except Exception as e:
        log.warning(f"{key}: fetch failed — {e}")
        return []


async def fetch_ooni(client: httpx.AsyncClient, cutoff: datetime) -> list[dict]:
    ooni_cfg = next((f for f in FEEDS if f["key"] == "ooni_api"), None)
    if not ooni_cfg:
        return []
    try:
        resp = await client.get(ooni_cfg["url"], timeout=20, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        items = []
        for m in data.get("results", [])[:30]:
            if not m.get("anomaly"):
                continue
            raw_ts = m.get("measurement_start_time", "")
            try:
                pub_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except Exception:
                pub_dt = None
            if pub_dt and pub_dt < cutoff:
                continue
            items.append({
                "source":    "ooni_api",
                "lang":      "en",
                "title":     f"OONI anomaly: {m.get('input', 'unknown')} on {m.get('probe_asn', '')}",
                "url":       f"https://explorer.ooni.org/measurement/{m.get('report_id', '')}",
                "summary":   (f"Test: {m.get('test_name')} | ASN: {m.get('probe_asn')} | "
                              f"Confirmed blocked: {m.get('confirmed')}"),
                "published": raw_ts,
            })
        log.info(f"ooni_api: {len(items)} fresh anomalies")
        return items
    except Exception as e:
        log.warning(f"ooni_api: fetch failed — {e}")
        return []


REDDIT_SUBS = [
    {"subreddit": "myanmar", "filter": None},
]

# Minimum quality thresholds — keeps signal, drops shitposts
# r/myanmar and r/burma are small communities; lower bar than general subs
REDDIT_MIN_SCORE    = 3    # upvotes (net positive is enough)
REDDIT_MIN_COMMENTS = 2


async def fetch_reddit(client: httpx.AsyncClient, cutoff: datetime) -> list[dict]:
    items = []
    for cfg in REDDIT_SUBS:
        sub = cfg["subreddit"]
        kw  = cfg["filter"]
        url = f"https://www.reddit.com/r/{sub}.json?limit=50"
        try:
            resp = await client.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])
            count = 0
            for child in posts:
                p = child.get("data", {})

                # Quality gates
                if p.get("score", 0) < REDDIT_MIN_SCORE:
                    continue
                if p.get("num_comments", 0) < REDDIT_MIN_COMMENTS:
                    continue
                if p.get("stickied") or p.get("distinguished"):
                    continue

                # Age gate
                created = p.get("created_utc")
                pub_dt  = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
                if pub_dt and pub_dt < cutoff:
                    continue

                title   = p.get("title", "").strip()
                selftext = (p.get("selftext") or "").strip()[:400]
                combined = (title + " " + selftext).lower()

                # Keyword filter — broad subs use explicit filter word;
                # myanmar/burma subs require at least one topic keyword
                TOPIC_KEYWORDS = [
                    "internet", "vpn", "censorship", "blocked", "shutdown",
                    "telecom", "mpt", "ooredoo", "mytel", "network", "firewall",
                    "digital", "surveillance", "junta", "connectivity", "bandwidth",
                    "social media", "facebook", "twitter", "telegram",
                ]
                if not any(k in combined for k in TOPIC_KEYWORDS):
                    continue

                items.append({
                    "source":    f"reddit_r_{sub}",
                    "lang":      "en",
                    "title":     title,
                    "url":       f"https://reddit.com{p.get('permalink', '')}",
                    "summary":   selftext or f"r/{sub} · {p.get('score')} upvotes · {p.get('num_comments')} comments",
                    "published": pub_dt.isoformat() if pub_dt else None,
                })
                count += 1
            log.info(f"reddit r/{sub}: {count} qualifying posts")
        except Exception as e:
            log.warning(f"reddit r/{sub}: fetch failed — {e}")
    return items


async def fetch_all(cutoff: datetime) -> list[dict]:
    rss_feeds = [f for f in FEEDS if f.get("type") == "rss"]
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; IIMBot/2.0; +https://internetinmyanmar.com)"},
        timeout=15,
    ) as client:
        tasks = [fetch_feed(f, client, cutoff) for f in rss_feeds]
        tasks.append(fetch_ooni(client, cutoff))
        tasks.append(fetch_reddit(client, cutoff))
        results = await asyncio.gather(*tasks)
    items = [item for batch in results for item in batch]
    log.info(f"Total fetched: {len(items)} items")
    return items


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        key = item["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

SCORE_PROMPT = """You are a relevance filter for a Myanmar internet-freedom monitoring site.

Score this news item on how relevant it is to:
- Internet shutdowns, censorship, or network blocking in Myanmar
- Telecom infrastructure or connectivity in Myanmar
- Digital rights, press freedom, or surveillance in Myanmar
- Myanmar military junta's control over communications

Return JSON only — no preamble:
{
  "score": <float 0-10>,
  "reason": "<one sentence max>",
  "category": "<one of: Censorship & Shutdowns | Telecom & Infrastructure | Digital Economy | News - Mobile | News - Broadband | News - Policy | Not relevant>"
}

Score guide:
  8-10  Directly about Myanmar internet freedom / censorship / shutdowns
  5-7   Related Myanmar digital/telecom news worth monitoring
  2-4   Tangentially related or very general
  0-1   Unrelated (travel, crypto, other countries, too vague)"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
def score_item(item: dict) -> dict:
    text = f"Title: {item['title']}\nSource: {item['source']}\nSummary: {item['summary']}"
    response = CLIENT.chat.completions.create(
        model="deepseek-chat",
        max_tokens=CONFIG.get("models", {}).get("max_tokens", {}).get("score", 150),
        messages=[
            {"role": "system", "content": "Respond with JSON only. No preamble."},
            {"role": "user",   "content": f"{SCORE_PROMPT}\n\nItem:\n{text}"},
        ],
    )
    scored = json.loads(response.choices[0].message.content)
    return {**item, **scored}


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def notify_telegram(text: str) -> None:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram env vars not set — skipping")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                  "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


def build_telegram_digest(relevant: list[dict], cutoff: datetime) -> str:
    since = cutoff.strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📡 *IIM Daily Monitor* — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
             f"_{len(relevant)} relevant items in the last {MAX_AGE_HOURS}h (since {since})_\n"]

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for item in relevant:
        cat = item.get("category", "Uncategorised")
        by_cat.setdefault(cat, []).append(item)

    CAT_EMOJI = {
        "Censorship & Shutdowns":   "🔴",
        "Telecom & Infrastructure": "📶",
        "Digital Economy":          "💻",
        "News - Mobile":            "📱",
        "News - Broadband":         "🌐",
        "News - Policy":            "🏛",
        "Not relevant":             "⬜",
    }

    for cat, cat_items in sorted(by_cat.items()):
        emoji = CAT_EMOJI.get(cat, "📌")
        lines.append(f"{emoji} *{cat}*")
        for item in cat_items:
            score = item.get("score", 0)
            title = item["title"][:80]
            url   = item.get("url", "")
            lang        = f" `[{item['lang']}]`" if item.get("lang") == "my" else ""
            display_url = gt_url(url) if item.get("lang") == "my" else url
            lines.append(f"  • [{title}]({display_url}) _{score:.1f}_{lang}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False) -> None:
    global CLIENT
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    CLIENT = OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    log.info(f"=== Monitor starting — lookback {MAX_AGE_HOURS}h (since {cutoff.isoformat()}) ===")

    items = asyncio.run(fetch_all(cutoff))
    items = deduplicate(items)
    log.info(f"After dedup: {len(items)} items")

    if not items:
        log.info("Nothing fetched — exiting")
        log.info("📡 IIM Monitor — no new items in the last 24 h.")  # Telegram disabled
        return

    scored = []
    for item in items:
        try:
            scored.append(score_item(item))
        except Exception as e:
            log.warning(f"Scoring failed for '{item['title'][:50]}': {e}")

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    OUTPUT_PATH.write_text(json.dumps(scored, indent=2, ensure_ascii=False))
    log.info(f"Saved {len(scored)} scored items → {OUTPUT_PATH}")

    relevant = [s for s in scored if s.get("score", 0) >= MIN_SCORE]
    log.info(f"{len(relevant)} items above threshold {MIN_SCORE}")

    if dry_run:
        log.info("Dry run — Telegram skipped")
        for item in relevant[:10]:
            log.info(f"  [{item.get('score', 0):.1f}] {item['title'][:70]}")
        return

    if not relevant:
        log.info("📡 IIM Monitor — %d items scanned, none above threshold.", len(scored))
    else:
        log.info("📡 IIM Monitor — %d relevant items found (saved to monitor_output.json)", len(relevant))

    log.info("=== Monitor done ===")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
