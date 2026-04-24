"""
agents/digest_scanner.py

Daily digest. Reads monitor_output.json (written by monitor.py at 6:30 AM),
filters for relevant items (score >= 6), saves a pending JSON, and sends a
Telegram notification with title + URL.

Cron: 0 8 * * *   →  8:00 AM daily
  0 8 * * * ~/agents/venv/bin/python ~/agents/digest_scanner.py >> ~/logs/digest_scanner.log 2>&1

Usage:
  python digest_scanner.py             # full run
  python digest_scanner.py --dry-run   # filter + format, no Telegram, no file write
"""

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

AGENTS_DIR  = Path(__file__).parent
MONITOR_OUT = AGENTS_DIR / "monitor_output.json"
PENDING_DIR = AGENTS_DIR / "digest"
PENDING_DIR.mkdir(exist_ok=True)

MIN_SCORE = 6.0


def gt_url(url: str) -> str:
    return f"https://translate.google.com/translate?sl=my&tl=en&u={quote(url, safe='')}"


def _translate_title(title: str) -> str:
    try:
        import sys
        sys.path.insert(0, str(AGENTS_DIR))
        from utils.model_router import call
        return call(
            "translate_mm",
            "Translate this Myanmar/Burmese title to English. Return only the translated title, no explanation.",
            content=title,
            max_tokens=120,
        ).strip()
    except Exception:
        return title


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
        if c.get("lang") == "my":
            title = f"{_translate_title(title)} `[my→en]`"
            url   = gt_url(url)
        lines.append(f"*{i}.* {title}")
        lines.append(url)
        lines.append("")
    return "\n".join(lines)


def run(dry_run: bool = False):
    today = date.today().isoformat()
    log.info("=== Digest scanner starting (%s) ===", today)

    if not MONITOR_OUT.exists():
        log.warning("monitor_output.json not found — did monitor.py run today?")
        if not dry_run:
            telegram_send(f"📭 *IIM Daily Digest — {today}*\n\nNo monitor data available.")
        return

    all_scored = json.loads(MONITOR_OUT.read_text())
    log.info("Loaded %d items from monitor_output.json", len(all_scored))

    candidates = [
        {
            "title":           item.get("title", ""),
            "url":             item.get("url", ""),
            "source":          item.get("source", ""),
            "published":       item.get("published", ""),
            "summary":         item.get("summary", "")[:300],
            "relevance_score": item.get("score", 0),
            "category":        item.get("category", "Other"),
            "reason":          item.get("reason", ""),
            "lang":            item.get("lang", "en"),
        }
        for item in all_scored
        if item.get("score", 0) >= MIN_SCORE
    ]
    candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
    log.info("Candidates: %d", len(candidates))

    if not candidates:
        log.info("No candidates above threshold %.1f", MIN_SCORE)
        if not dry_run:
            telegram_send(f"📭 *IIM Daily Digest — {today}*\n\nNo new articles found today.")
        return

    pending_file = PENDING_DIR / f"pending_{today}.json"
    if not dry_run:
        pending_file.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
        log.info("Saved pending: %s", pending_file)

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
