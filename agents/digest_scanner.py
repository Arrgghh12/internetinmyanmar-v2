"""
agents/digest_scanner.py

Daily digest scanner.
Fetches from RSS feeds (feeds.yaml), scores for relevance, deduplicates,
saves a pending JSON file, and sends a Telegram notification with title + URL.

Cron: 0 8 * * *   →  8:00 AM daily
  0 8 * * * ~/agents/venv/bin/python ~/agents/digest_scanner.py >> ~/logs/digest_scanner.log 2>&1

Usage:
  python digest_scanner.py             # full run
  python digest_scanner.py --dry-run   # fetch + score, no Telegram, no seen update
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import httpx
import requests
import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Paths & config ─────────────────────────────────────────────────────────────

AGENTS_DIR  = Path(__file__).parent
FEEDS       = yaml.safe_load((AGENTS_DIR / "feeds.yaml").read_text()).get("feeds", [])
PENDING_DIR = AGENTS_DIR / "digest"
PENDING_DIR.mkdir(exist_ok=True)
SEEN_FILE   = AGENTS_DIR / "backfill" / "seen_urls.txt"   # shared with backfill scanner

# ── Seen-URL dedup ─────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    return set(SEEN_FILE.read_text().splitlines())

def mark_seen(url: str, seen: set, dry_run: bool):
    h = url_hash(url)
    seen.add(h)
    if not dry_run:
        with open(SEEN_FILE, "a") as f:
            f.write(h + "\n")

# ── Relevance scoring ──────────────────────────────────────────────────────────

SCORE_PROMPT = """Score this article for relevance to Myanmar internet freedom,
digital censorship, network shutdowns, VPN/social media blocking,
journalist digital safety, or surveillance technology.

Title: {title}
Source: {source}
Excerpt: {excerpt}
Date: {date}

category MUST be exactly one of: Shutdown | Censorship | Arrest | Policy | Data | Surveillance | Other

Return JSON only:
{{
  "relevance_score": 0,
  "category": "Shutdown",
  "tags": ["tag1", "tag2"],
  "reason": "one sentence",
  "your_title": "reworded title for our site (different from original, same meaning)"
}}"""

def score_article(item: dict, client: OpenAI) -> dict | None:
    prompt = SCORE_PROMPT.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        excerpt=(item.get("summary") or item.get("content") or "")[:400],
        date=item.get("published", ""),
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=250,
            messages=[
                {"role": "system", "content": "Respond with JSON only. No preamble."},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(raw)
    except Exception as e:
        log.warning("Score parse failed for '%s': %s", item.get("title", "")[:50], e)
        return None

# ── RSS fetching ───────────────────────────────────────────────────────────────

async def fetch_rss_source(name: str, url: str, cutoff: datetime,
                            client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        items = []
        for entry in feed.entries[:30]:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            pub_dt    = datetime(*published[:6], tzinfo=timezone.utc) if published else None
            if pub_dt and pub_dt < cutoff:
                continue
            raw_summary = entry.get("summary") or ""
            # Strip HTML before truncating so we never cut inside a tag
            import re as _re, html as _html
            clean_summary = _re.sub(r"<[^>]+>", "", raw_summary)
            clean_summary = _re.sub(r"<[^>]*$", "", clean_summary)  # truncated tags
            clean_summary = _html.unescape(clean_summary).strip()
            items.append({
                "source":    name,
                "title":     entry.get("title", ""),
                "url":       entry.get("link", ""),
                "summary":   clean_summary[:500],
                "published": pub_dt.isoformat() if pub_dt else "",
            })
        log.info("%s: %d items", name, len(items))
        return items
    except Exception as e:
        log.warning("%s: fetch failed — %s", name, e)
        return []


async def fetch_all_rss(cutoff: datetime) -> list[dict]:
    """Fetch RSS from all feeds in feeds.yaml."""
    pairs: list[tuple[str, str]] = []
    for feed in FEEDS:
        if feed.get("type") != "rss":
            continue
        pairs.append((feed["key"], feed["url"]))

    async with httpx.AsyncClient(headers={"User-Agent": "IIMBot/1.0"}) as http:
        results = await asyncio.gather(*[
            fetch_rss_source(name, url, cutoff, http) for name, url in pairs
        ])
    return [item for batch in results for item in batch]

# ── Telegram ───────────────────────────────────────────────────────────────────

def telegram_send(text: str) -> None:
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.warning("Telegram not configured — message:\n%s", text[:200])
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                  "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as e:
        log.error("Telegram send failed: %s", e)


def build_telegram_message(candidates: list[dict], today: str) -> str:
    lines = [f"📰 *IIM Daily Digest — {today}*"]
    lines.append(f"{len(candidates)} article{'s' if len(candidates) != 1 else ''} matched\n")

    for i, c in enumerate(candidates, 1):
        title = c.get("title", "")
        url   = c.get("url", "")
        lines.append(f"*{i}.* {title}")
        lines.append(url)
        lines.append("")

    return "\n".join(lines)

# ── Main ───────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False):
    today   = date.today().isoformat()
    cutoff  = datetime.now(timezone.utc) - timedelta(hours=48)
    seen    = load_seen()

    client = OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )

    # 1. Fetch
    log.info("=== Digest scanner starting (%s) ===", today)
    all_items = asyncio.run(fetch_all_rss(cutoff))
    log.info("Total fetched: %d items", len(all_items))

    # 2. Deduplicate
    unique: list[dict] = []
    for item in all_items:
        url = item.get("url", "")
        if not url:
            continue
        h = url_hash(url)
        if h in seen:
            continue
        mark_seen(url, seen, dry_run)
        unique.append(item)

    log.info("After dedup: %d unique items", len(unique))

    # 3. Score
    candidates: list[dict] = []
    for item in unique:
        scored = score_article(item, client)
        if scored is None:
            continue
        score = min(10, scored.get("relevance_score", 0))
        if score < 6:
            log.info("  ✗ [%d/10] %s", score, item.get("title", "")[:60])
            continue

        # Resolve source name from source_scores if available
        domain = urlparse(item["url"]).netloc.replace("www.", "")
        source_db_path = AGENTS_DIR / "data" / "source_scores.json"
        source_name = domain
        if source_db_path.exists():
            db = json.loads(source_db_path.read_text())
            source_name = db.get(domain, {}).get("name", domain)

        candidate = {
            "title":           item.get("title", ""),
            "your_title":      scored.get("your_title") or item.get("title", ""),
            "url":             item["url"],
            "source":          item.get("source", ""),
            "source_name":     source_name,
            "published":       item.get("published", ""),
            "summary":         item.get("summary", "")[:300],
            "relevance_score": score,
            "category":        scored.get("category", "Other"),
            "tags":            scored.get("tags", []),
            "reason":          scored.get("reason", ""),
        }
        candidates.append(candidate)
        log.info("  ✓ [%d/10] %s", score, item.get("title", "")[:60])

    # Sort by score desc
    candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
    log.info("Candidates: %d", len(candidates))

    if not candidates:
        msg = f"📭 *IIM Daily Digest — {today}*\n\nNo new articles found today."
        log.info("No candidates — sending empty notification")
        if not dry_run:
            telegram_send(msg)
        return

    # 4. Save pending JSON
    pending_file = PENDING_DIR / f"pending_{today}.json"
    if not dry_run:
        pending_file.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
        log.info("Saved pending: %s", pending_file)

    # 5. Send Telegram
    msg = build_telegram_message(candidates, today)
    if dry_run:
        print("\n--- DRY RUN: Telegram message ---")
        print(msg)
        print("---")
    else:
        telegram_send(msg)
        log.info("Telegram notification sent")

    log.info("=== Digest scanner done ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
