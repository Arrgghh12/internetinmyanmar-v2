"""
IIM Telegram Editorial Bot
--------------------------
Runs as a long-lived process on the VPS (systemd service).
Manages the full editorial workflow via Telegram:
  1. Sends briefs to Anna with [Approve][Adjust][Reject] buttons
  2. Collects adjustment notes if needed
  3. Triggers writer.py to generate articles
  4. Sends draft + 3 Unsplash image suggestions
  5. Handles [Publish][Need changes]
  6. Triggers publisher.py and sends live URL

Bot commands:
  /status  — list pending briefs
  /drafts  — list articles awaiting approval
  /today   — summary of today's run
  /test    — connectivity check (send this to verify bot is live)
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])

AGENTS_DIR = Path(__file__).parent
BRIEFS_DIR = AGENTS_DIR / "briefs"
APPROVED_DIR = AGENTS_DIR / "approved"
DB_PATH = AGENTS_DIR / "bot_state.db"

VENV_PYTHON = AGENTS_DIR / "venv" / "bin" / "python"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ConversationHandler states
AWAITING_ADJUSTMENT = 1
AWAITING_IMAGE_PICK = 2
AWAITING_REVISION = 3


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS briefs (
                id          TEXT PRIMARY KEY,
                slug        TEXT,
                title       TEXT,
                path        TEXT,
                state       TEXT DEFAULT 'pending',
                adjustments TEXT,
                article_path TEXT,
                image_url   TEXT,
                image_credit TEXT,
                message_id  INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def upsert_brief(brief_id: str, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        updates = ", ".join(f"{k}=excluded.{k}" for k in data if k != "id")
        await db.execute(
            f"INSERT INTO briefs (id, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            [brief_id, *data.values()],
        )
        await db.commit()


async def get_brief(brief_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM briefs WHERE id=?", [brief_id]) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_briefs(state: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM briefs WHERE state=? ORDER BY created_at DESC", [state]
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Public API — called by brief_generator.py and publisher.py
# ---------------------------------------------------------------------------

async def send_brief(brief: dict):
    """
    Called by brief_generator.py after saving a brief file.
    brief = { id, slug, title, excerpt, path, tags, category, angle }
    """
    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()

    brief_id = brief["id"]
    text = (
        f"📋 *New brief ready*\n\n"
        f"*{brief['title']}*\n\n"
        f"_{brief.get('excerpt', '')}_ \n\n"
        f"Category: {brief.get('category', '—')}\n"
        f"Tags: {', '.join(brief.get('tags', []))}"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{brief_id}"),
            InlineKeyboardButton("✏️ Adjust",  callback_data=f"adjust:{brief_id}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{brief_id}"),
        ]
    ])
    msg = await app.bot.send_message(
        chat_id=CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    await upsert_brief(brief_id, {
        "slug": brief["slug"],
        "title": brief["title"],
        "path": brief["path"],
        "state": "pending",
        "message_id": msg.message_id,
    })
    await app.shutdown()


async def send_confirmation(slug: str, pr_url: str):
    """Called by publisher.py after opening the GitHub PR."""
    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"🚀 *Article queued for publish*\n\n"
            f"PR opened: {pr_url}\n\n"
            f"Cloudflare will build in ~90 seconds after Anna merges."
        ),
        parse_mode="Markdown",
    )
    await app.shutdown()


# ---------------------------------------------------------------------------
# Bot command handlers
# ---------------------------------------------------------------------------

async def cmd_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    await update.message.reply_text("IIM Bot is live ✓")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    pending = await list_briefs("pending")
    if not pending:
        await update.message.reply_text("No pending briefs.")
        return
    lines = [f"• {b['title']}" for b in pending]
    await update.message.reply_text("*Pending briefs:*\n" + "\n".join(lines), parse_mode="Markdown")


async def cmd_drafts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    review = await list_briefs("review")
    if not review:
        await update.message.reply_text("No drafts awaiting approval.")
        return
    lines = [f"• {b['title']}" for b in review]
    await update.message.reply_text("*Drafts awaiting approval:*\n" + "\n".join(lines), parse_mode="Markdown")


async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    pending = await list_briefs("pending")
    review = await list_briefs("review")
    published = await list_briefs("published")
    await update.message.reply_text(
        f"*Today's summary*\n"
        f"Pending briefs: {len(pending)}\n"
        f"Awaiting approval: {len(review)}\n"
        f"Published today: {len(published)}",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Callback query handlers (inline keyboard buttons)
# ---------------------------------------------------------------------------

async def handle_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, brief_id = query.data.split(":", 1)
    brief = await get_brief(brief_id)
    if not brief:
        await query.edit_message_text("Brief not found.")
        return

    await upsert_brief(brief_id, {"state": "writing"})
    await query.edit_message_text(
        f"✅ *Approved:* {brief['title']}\n\nGenerating article…",
        parse_mode="Markdown",
    )
    ctx.application.create_task(_write_and_send(query, brief_id, brief))


async def handle_adjust(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, brief_id = query.data.split(":", 1)
    await upsert_brief(brief_id, {"state": "adjusting"})
    ctx.user_data["adjusting_brief_id"] = brief_id
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(
        "What should change in this brief? (angle, focus, length, missing context…)"
    )
    return AWAITING_ADJUSTMENT


async def handle_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, brief_id = query.data.split(":", 1)
    brief = await get_brief(brief_id)
    await upsert_brief(brief_id, {"state": "rejected"})
    await query.edit_message_text(f"❌ *Rejected:* {brief['title']}", parse_mode="Markdown")


async def receive_adjustment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    brief_id = ctx.user_data.get("adjusting_brief_id")
    if not brief_id:
        return ConversationHandler.END
    adjustments = update.message.text
    brief = await get_brief(brief_id)
    await upsert_brief(brief_id, {"state": "writing", "adjustments": adjustments})
    await update.message.reply_text("✏️ Got it — regenerating with your adjustments…")
    asyncio.create_task(_write_and_send(update, brief_id, brief, adjustments))
    return ConversationHandler.END


async def handle_publish(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, brief_id = query.data.split(":", 1)
    brief = await get_brief(brief_id)
    await upsert_brief(brief_id, {"state": "publishing"})
    await query.edit_message_text(
        f"🚀 Publishing *{brief['title']}*…",
        parse_mode="Markdown",
    )
    asyncio.create_task(_publish(query, brief_id, brief))


async def handle_need_changes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, brief_id = query.data.split(":", 1)
    await upsert_brief(brief_id, {"state": "revising"})
    ctx.user_data["revising_brief_id"] = brief_id
    await query.edit_message_reply_markup(None)
    await query.message.reply_text("What needs to change in the article?")
    return AWAITING_REVISION


async def receive_revision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    brief_id = ctx.user_data.get("revising_brief_id")
    if not brief_id:
        return ConversationHandler.END
    revisions = update.message.text
    brief = await get_brief(brief_id)
    await upsert_brief(brief_id, {"state": "writing", "adjustments": revisions})
    await update.message.reply_text("Revising article…")
    asyncio.create_task(_write_and_send(update, brief_id, brief, revisions))
    return ConversationHandler.END


async def handle_image_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    brief_id = ctx.user_data.get("image_pick_brief_id")
    text = update.message.text.strip().lower()
    if text == "skip" or brief_id is None:
        ctx.user_data.pop("image_pick_brief_id", None)
        await _send_article_for_review(update, brief_id)
        return ConversationHandler.END

    images = ctx.user_data.get("image_options", [])
    try:
        idx = int(text) - 1
        if 0 <= idx < len(images):
            chosen = images[idx]
            await upsert_brief(brief_id, {
                "image_url": chosen["url"],
                "image_credit": chosen["credit"],
            })
    except ValueError:
        pass

    ctx.user_data.pop("image_pick_brief_id", None)
    ctx.user_data.pop("image_options", None)
    await _send_article_for_review(update, brief_id)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _write_and_send(context, brief_id: str, brief: dict, adjustments: str = ""):
    """Run writer.py and send draft + image suggestions."""
    cmd = [str(VENV_PYTHON), str(AGENTS_DIR / "writer.py"),
           "--brief-id", brief_id]
    if adjustments:
        cmd += ["--adjustments", adjustments]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.error("writer.py failed: %s", stderr.decode())
        await context.message.reply_text(
            f"❌ Article generation failed.\n```{stderr.decode()[:500]}```",
            parse_mode="Markdown",
        )
        return

    result = json.loads(stdout.decode())
    article_path = result["path"]
    await upsert_brief(brief_id, {"state": "image_pick", "article_path": article_path})

    # Send image suggestions
    from utils.unsplash_client import search_photos
    tags = brief.get("tags", [])
    query = " ".join(tags[:2]) + " Myanmar" if tags else "Myanmar internet"
    photos = search_photos(query, count=3)

    if photos:
        context.user_data["image_pick_brief_id"] = brief_id
        context.user_data["image_options"] = photos
        await context.message.reply_text(
            f"📝 Draft ready for *{brief['title']}*\n\nChoose an image (reply 1, 2, or 3) or type *skip*:",
            parse_mode="Markdown",
        )
        for i, photo in enumerate(photos, 1):
            await context.message.reply_photo(
                photo["thumb"],
                caption=f"{i}. {photo['credit']}",
            )
    else:
        await _send_article_for_review(context, brief_id)


async def _send_article_for_review(context, brief_id: str):
    brief = await get_brief(brief_id)
    article_path = brief.get("article_path")
    title = brief.get("title", "Article")

    if article_path and Path(article_path).exists():
        with open(article_path, "rb") as f:
            await context.message.reply_document(
                document=f,
                filename=f"{brief['slug']}.txt",
                caption=f"📄 Draft: *{title}*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🚀 Publish", callback_data=f"publish:{brief_id}"),
                        InlineKeyboardButton("✏️ Need changes", callback_data=f"revise:{brief_id}"),
                    ]
                ]),
            )
    await upsert_brief(brief_id, {"state": "review"})


async def _publish(context, brief_id: str, brief: dict):
    cmd = [str(VENV_PYTHON), str(AGENTS_DIR / "publisher.py"), "--brief-id", brief_id]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        await context.message.reply_text(
            f"❌ Publish failed.\n```{stderr.decode()[:500]}```",
            parse_mode="Markdown",
        )
        return

    result = json.loads(stdout.decode())
    pr_url = result.get("pr_url", "")
    await upsert_brief(brief_id, {"state": "published"})
    await context.message.reply_text(
        f"✅ PR opened: {pr_url}\n\nMerge it in GitHub → Cloudflare rebuilds in ~90s.",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if "--test" in sys.argv:
        async def _test():
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            await app.bot.send_message(chat_id=CHAT_ID, text="IIM Bot is live ✓")
            await app.shutdown()
        asyncio.run(_test())
        return

    asyncio.run(init_db())

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("test",   cmd_test))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("drafts", cmd_drafts))
    app.add_handler(CommandHandler("today",  cmd_today))

    adj_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_adjust, pattern=r"^adjust:")],
        states={AWAITING_ADJUSTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_adjustment)]},
        fallbacks=[],
    )
    rev_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_need_changes, pattern=r"^revise:")],
        states={AWAITING_REVISION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_revision)]},
        fallbacks=[],
    )
    img_conv = ConversationHandler(
        entry_points=[],
        states={AWAITING_IMAGE_PICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_image_pick)]},
        fallbacks=[],
    )

    app.add_handler(adj_conv)
    app.add_handler(rev_conv)
    app.add_handler(img_conv)
    app.add_handler(CallbackQueryHandler(handle_approve, pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(handle_reject,  pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(handle_publish, pattern=r"^publish:"))

    log.info("IIM Telegram bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
