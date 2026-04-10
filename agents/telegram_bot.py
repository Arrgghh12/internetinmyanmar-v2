"""
agents/telegram_bot.py

IIM Digest Approval Bot.
Runs as a long-running service on the VPS.

Usage:
  python telegram_bot.py          # polling mode (recommended for VPS)

Systemd service: see /etc/systemd/system/iim-bot.service

Approval flow:
  1. digest_scanner.py sends a numbered list of articles via Telegram
  2. You reply with numbers ("1 3 5"), "all", or "skip"
  3. Bot publishes selected articles directly to GitHub → triggers Cloudflare rebuild

Commands:
  /pending   — show today's pending articles (if any)
  /help      — show this help
"""

import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from github import Github, GithubException
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ── Config ─────────────────────────────────────────────────────────────────────

BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_CHAT = int(os.environ["TELEGRAM_CHAT_ID"])

AGENTS_DIR   = Path(__file__).parent
PENDING_DIR  = AGENTS_DIR / "digest"
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME    = "Arrgghh12/internetinmyanmar-v2"
BRANCH       = os.environ.get("PUBLISH_BRANCH", "dev")   # switch to "main" after DNS cutover
DIGEST_PATH  = "src/content/digest"


# ── Auth ───────────────────────────────────────────────────────────────────────

def authorized(update: Update) -> bool:
    return (update.effective_chat is not None
            and update.effective_chat.id == ALLOWED_CHAT)


# ── Pending file helpers ───────────────────────────────────────────────────────

def latest_pending() -> tuple[Path | None, list[dict]]:
    """Return the most recent pending JSON and its contents."""
    files = sorted(PENDING_DIR.glob("pending_*.json"), reverse=True)
    if not files:
        return None, []
    f = files[0]
    return f, json.loads(f.read_text())


# ── MDX builder (mirrors backfill_publisher.py logic) ─────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags (including truncated/unclosed ones) and decode entities."""
    import re, html
    # Remove complete tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove any truncated tag remnant (e.g. "<img alt=..." cut before closing >)
    text = re.sub(r"<[^>]*$", "", text)
    return html.unescape(text).strip()


def make_mdx(c: dict, added_at: str) -> str:
    tags      = [t.strip() for t in c.get("tags", [])]
    tags_yaml = "\n".join([f'  - "{t}"' for t in tags])
    excerpt   = strip_html(c.get("summary") or "").strip()
    if excerpt and not excerpt.endswith((".", "...", "?", "!")):
        excerpt = excerpt.rsplit(" ", 1)[0] + "..."

    title_safe  = c["your_title"].replace('"', "'")
    source_safe = c["title"].replace('"', "'")

    source_db_path = AGENTS_DIR / "data" / "source_scores.json"
    source_info: dict = {}
    if source_db_path.exists():
        from urllib.parse import urlparse
        domain = urlparse(c["url"]).netloc.replace("www.", "")
        db = json.loads(source_db_path.read_text())
        source_info = db.get(domain, {})

    source_score = source_info.get("total", 50)
    source_tier  = source_info.get("tier",  "C")
    source_label = source_info.get("label", "Use with Caution")
    source_name  = source_info.get("name",  c.get("source_name", c.get("source", "")))

    published_at = (c.get("published") or added_at)[:10]

    return f"""---
title: "{title_safe}"
sourceTitle: "{source_safe}"
source: "{source_name}"
sourceUrl: "{c['url']}"
canonical: "{c['url']}"
publishedAt: {published_at}
addedAt: {added_at}
category: "{c.get('category', 'Other')}"
tags:
{tags_yaml}
sourceScore: {source_score}
sourceTier: "{source_tier}"
sourceLabel: "{source_label}"
type: "digest"
draft: false
---

*Originally published by [{source_name}]({c['url']}) on {published_at}.*

> {excerpt}

[Read the full article on {source_name} →]({c['url']})
"""


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:60].strip("-")


# ── GitHub publish ─────────────────────────────────────────────────────────────

def publish_to_github(selected: list[dict]) -> tuple[int, list[str]]:
    """
    Create MDX files in src/content/digest/ on the main branch via GitHub API.
    Returns (count_published, list_of_filenames).
    """
    g        = Github(GITHUB_TOKEN)
    repo     = g.get_repo(REPO_NAME)
    today    = date.today().isoformat()
    created  = 0
    filenames: list[str] = []

    for c in selected:
        pub_date = (c.get("published") or today)[:10]
        slug     = slugify(c.get("your_title") or c.get("title", ""))
        filename = f"{pub_date}-{slug}.mdx"
        path     = f"{DIGEST_PATH}/{filename}"
        content  = make_mdx(c, today)

        try:
            repo.get_contents(path, ref=BRANCH)
            log.info("Already exists, skipping: %s", filename)
            continue
        except GithubException:
            pass   # doesn't exist yet → create it

        try:
            repo.create_file(
                path,
                f"digest: {c.get('your_title', '')[:60]}",
                content,
                branch=BRANCH,
            )
            created += 1
            filenames.append(filename)
            log.info("Published: %s", filename)
        except Exception as e:
            log.error("Failed to publish %s: %s", filename, e)

    return created, filenames


# ── Handlers ───────────────────────────────────────────────────────────────────

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    pending_file, candidates = latest_pending()
    if not candidates:
        await update.message.reply_text("No pending articles found.")
        return
    lines = [f"📋 *Pending: {pending_file.stem}*\n"]
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"*{i}.* {c.get('your_title', c.get('title', ''))[:70]}\n"
            f"   {c['url']}"
        )
    lines.append("\nReply with numbers, `all`, or `skip`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                     disable_web_page_preview=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        "*IIM Digest Bot*\n\n"
        "When the daily scanner sends you a list of articles:\n"
        "• Reply `1 3 5` — publish articles 1, 3 and 5\n"
        "• Reply `all` — publish all articles\n"
        "• Reply `skip` — skip all for today\n\n"
        "/pending — show today's pending list\n"
        "/help — this message",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    text = (update.message.text or "").strip().lower()

    _, candidates = latest_pending()
    if not candidates:
        await update.message.reply_text("No pending articles. Scanner runs at 8 AM.")
        return

    # Parse reply: numbers, "all", or "skip"
    if text == "skip":
        await update.message.reply_text("⏭ Skipped. No articles published today.")
        return

    if text == "all":
        selected = candidates
    else:
        # Extract numbers
        nums = [int(n) for n in re.findall(r"\d+", text)]
        nums = [n for n in nums if 1 <= n <= len(candidates)]
        if not nums:
            await update.message.reply_text(
                "Didn't understand that. Reply with numbers like `1 3 5`, `all`, or `skip`."
            )
            return
        selected = [candidates[n - 1] for n in nums]

    await update.message.reply_text(f"⏳ Publishing {len(selected)} article(s)…")

    try:
        count, filenames = publish_to_github(selected)
    except Exception as e:
        log.error("Publish failed: %s", e)
        await update.message.reply_text(f"❌ Publish failed: {e}")
        return

    if count == 0:
        await update.message.reply_text(
            "⚠️ Nothing new published (articles may already exist)."
        )
        return

    lines = [f"✅ *{count} article(s) published to main*\n"]
    for fn in filenames:
        lines.append(f"• `{fn}`")
    lines.append("\nCloudflare Pages rebuild triggered automatically.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("IIM Digest Bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
