"""
IIM Telegram Pipeline Bot
--------------------------
Command interface to the full editorial pipeline.
Runs 24/7 on the VPS as a systemd service (polling mode).

Commands:
  DISCOVERY:    /draft /topic /translate /ooni /search
  BRIEFS:       /list /pick /show /approve /amend /merge /reject
  PIPELINE:     /status /run /pause /resume /log /sources
  ARTICLES:     /unpublish /archive /restore /archived
  HELP:         /help
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT = int(os.getenv("TELEGRAM_CHAT_ID", "0"))  # single user for now

BASE_DIR     = Path(__file__).parent
BRIEFS_DIR   = BASE_DIR / "briefs"
APPROVED_DIR = BASE_DIR / "approved"
REJECTED_DIR = BASE_DIR / "rejected"
LOGS_DIR     = Path.home() / "logs"
DB_PATH      = BASE_DIR / "bot_state.db"

ARTICLES_DIR = BASE_DIR.parent / "src" / "content" / "articles"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "bot.log") if LOGS_DIR.exists() else logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Auth guard ──────────────────────────────────────────────────────────────

def authorized(update: Update) -> bool:
    return update.effective_chat is not None and update.effective_chat.id == ALLOWED_CHAT


async def auth_reply(update: Update, text: str) -> None:
    """Send reply only if authorized."""
    if not authorized(update):
        return
    await update.message.reply_text(text, parse_mode="Markdown")


# ── Database ────────────────────────────────────────────────────────────────

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS briefs (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                slug    TEXT,
                title   TEXT,
                path    TEXT,
                source  TEXT,   -- 'cron' or 'manual'
                created TEXT,
                version INTEGER DEFAULT 1,
                status  TEXT DEFAULT 'pending'
            )
        """)
        await db.commit()


async def db_get(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM state WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def db_set(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


# ── Brief helpers ───────────────────────────────────────────────────────────

def get_pending_briefs() -> list[dict]:
    """Return list of brief dicts from the briefs/ folder."""
    briefs = []
    today = datetime.now().strftime("%Y-%m-%d")
    for day_dir in sorted(BRIEFS_DIR.glob("*"), reverse=True)[:3]:
        if not day_dir.is_dir():
            continue
        for brief_file in sorted(day_dir.glob("*.md")):
            # Skip if already approved/rejected
            approved = (APPROVED_DIR / day_dir.name / brief_file.name).exists()
            rejected = (REJECTED_DIR / day_dir.name / brief_file.name).exists()
            if approved or rejected:
                continue
            content = brief_file.read_text(encoding="utf-8")
            title = _extract_title(content, brief_file.stem)
            briefs.append({
                "path": str(brief_file),
                "slug": brief_file.stem,
                "title": title,
                "date": day_dir.name,
                "source": "cron" if day_dir.name < today else "manual",
            })
    return briefs


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')
    return fallback.replace("-", " ").title()


def _read_brief(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return "(could not read brief)"


# ── Subprocess helpers ──────────────────────────────────────────────────────

def run_agent(script: str, *args: str, timeout: int = 300) -> tuple[int, str]:
    venv_python = BASE_DIR / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    cmd = [python, str(BASE_DIR / script), *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=BASE_DIR)
        output = (result.stdout + result.stderr).strip()
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, f"Timeout after {timeout}s"
    except Exception as e:
        return -1, str(e)


def tail_log(log_name: str, n: int = 20) -> str:
    log_file = LOGS_DIR / f"{log_name}.log"
    if not log_file.exists():
        return f"No log file: {log_file}"
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:]) if lines else "(empty)"


# ── /draft ──────────────────────────────────────────────────────────────────

async def cmd_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    args_text = " ".join(context.args or [])
    if not args_text:
        await auth_reply(update, "Usage: `/draft [url(s)] [notes]`\nExample: `/draft https://netblocks.org/xyz looks significant`")
        return

    await update.message.reply_text("⏳ Fetching and building brief…")
    rc, out = run_agent("brief_generator.py", "--manual", args_text, timeout=120)
    if rc == 0:
        briefs = get_pending_briefs()
        if briefs:
            latest = briefs[0]
            content = _read_brief(latest["path"])
            await update.message.reply_text(
                f"📋 *Brief ready:*\n\n{content[:3000]}",
                parse_mode="Markdown",
            )
            await update.message.reply_text(
                "→ `/approve` · `/amend [notes]` · `/reject [reason]`\n"
                "Use `/list` if you have other pending briefs.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(f"✅ Done.\n```\n{out[-500:]}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Brief generation failed:\n```\n{out[-800:]}\n```", parse_mode="Markdown")


# ── /topic ──────────────────────────────────────────────────────────────────

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args:
        await auth_reply(update, "Usage: `/topic [description]`\nExample: `/topic reports of shutdown in Chin State`")
        return

    topic = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching sources for: _{topic}_…", parse_mode="Markdown")
    rc, out = run_agent("brief_generator.py", "--topic", topic, timeout=120)
    if rc == 0:
        briefs = get_pending_briefs()
        if briefs:
            latest = briefs[0]
            content = _read_brief(latest["path"])
            await update.message.reply_text(f"📋 *Brief ready:*\n\n{content[:3000]}", parse_mode="Markdown")
            await update.message.reply_text("→ `/approve` · `/amend [notes]` · `/reject [reason]`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"✅\n```\n{out[-500:]}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Failed:\n```\n{out[-800:]}\n```", parse_mode="Markdown")


# ── /translate ──────────────────────────────────────────────────────────────

async def cmd_translate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args:
        await auth_reply(update, "Usage: `/translate [url or Burmese text]`")
        return

    content = " ".join(context.args)
    await update.message.reply_text("🔄 Translating…")

    # If it looks like a URL, fetch it first
    if content.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(content)
                fetched_text = r.text[:5000]
        except Exception as e:
            await update.message.reply_text(f"❌ Could not fetch URL: {e}")
            return
        prompt_text = fetched_text
    else:
        prompt_text = content

    # Simple pass-through to Claude via brief_generator if available
    rc, out = run_agent("brief_generator.py", "--translate", prompt_text[:2000], timeout=60)
    if rc == 0:
        await update.message.reply_text(f"*Translation:*\n\n{out[:3000]}", parse_mode="Markdown")
        await update.message.reply_text(f"→ Use `/draft {content.split()[0]}` to create an article from this.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Translation failed:\n```\n{out[-500:]}\n```", parse_mode="Markdown")


# ── /list ───────────────────────────────────────────────────────────────────

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    briefs = get_pending_briefs()
    if not briefs:
        await auth_reply(update, "📋 No pending briefs.\nUse `/draft [url]` or `/topic [description]` to create one.")
        return

    lines = [f"📋 *Pending briefs ({len(briefs)}):*\n"]
    for i, b in enumerate(briefs, 1):
        lines.append(f"[{i}] {b['title']} _{b['date']}_")
    lines.append("\nUse `/pick [n]` to select one.")

    active = await db_get("active_brief_path")
    if active:
        lines.append(f"Current active: `{Path(active).stem}`")
    else:
        lines.append("Current active: none")

    await auth_reply(update, "\n".join(lines))


# ── /pick ───────────────────────────────────────────────────────────────────

async def cmd_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args or not context.args[0].isdigit():
        await auth_reply(update, "Usage: `/pick [number]`\nUse `/list` first.")
        return

    n = int(context.args[0])
    briefs = get_pending_briefs()
    if n < 1 or n > len(briefs):
        await auth_reply(update, f"❌ No brief #{n}. Use `/list` to see options.")
        return

    brief = briefs[n - 1]
    await db_set("active_brief_path", brief["path"])
    content = _read_brief(brief["path"])
    await update.message.reply_text(f"📋 *Brief #{n} — now active:*\n\n{content[:3000]}", parse_mode="Markdown")
    await update.message.reply_text("→ `/approve` · `/amend [notes]` · `/reject [reason]`", parse_mode="Markdown")


# ── /show ───────────────────────────────────────────────────────────────────

async def cmd_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    path = await db_get("active_brief_path")
    if not path:
        await auth_reply(update, "No active brief. Use `/list` and `/pick [n]`.")
        return
    content = _read_brief(path)
    slug = Path(path).stem
    await update.message.reply_text(f"📋 *Brief: {slug}*\n\n{content[:3000]}", parse_mode="Markdown")


# ── /approve ─────────────────────────────────────────────────────────────────

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    path = await db_get("active_brief_path")
    if not path:
        # Auto-pick first pending brief if only one
        briefs = get_pending_briefs()
        if len(briefs) == 1:
            path = briefs[0]["path"]
            await db_set("active_brief_path", path)
        else:
            await auth_reply(update, "No active brief. Use `/list` and `/pick [n]`.")
            return

    tweaks = " ".join(context.args) if context.args else ""
    slug = Path(path).stem

    # Move to approved folder
    brief_file = Path(path)
    day = brief_file.parent.name
    approved_dir = APPROVED_DIR / day
    approved_dir.mkdir(parents=True, exist_ok=True)
    approved_path = approved_dir / brief_file.name

    if tweaks:
        # Append tweaks note to brief
        existing = brief_file.read_text(encoding="utf-8")
        brief_file.write_text(existing + f"\n\n## Article tweaks\n{tweaks}\n", encoding="utf-8")

    import shutil
    shutil.copy2(path, approved_path)

    await update.message.reply_text(f"✅ Brief approved. Writing article for _{slug}_…", parse_mode="Markdown")
    rc, out = run_agent("writer.py", str(approved_path), "--deepseek", timeout=300)
    if rc == 0:
        # Parse JSON result from writer.py stdout
        result = {}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{") and "preview_url" in line:
                try:
                    result = json.loads(line)
                except json.JSONDecodeError:
                    pass

        preview_url = result.get("preview_url", "")
        preview_slug = result.get("preview_slug", "")
        real_slug = result.get("real_slug", slug)

        # Store mapping so /publish knows what to rename
        await db_set("pending_preview_slug", preview_slug)
        await db_set("pending_real_slug", real_slug)
        await db_set("pending_mdx_path", result.get("mdx_path", ""))

        if preview_url:
            await update.message.reply_text(
                f"✅ Draft ready — preview link (secret, share only with Anna):\n\n"
                f"{preview_url}\n\n"
                f"Reply /publish to push to GitHub with slug `{real_slug}`, or send revision notes.",
            )
        else:
            await update.message.reply_text(f"✅ Done:\n```\n{out[-600:]}\n```", parse_mode="Markdown")
        await db_set("active_brief_path", "")
    else:
        await update.message.reply_text(f"❌ writer.py failed:\n```\n{out[-800:]}\n```", parse_mode="Markdown")


# ── /publish ─────────────────────────────────────────────────────────────────

async def cmd_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rename preview-{token}.mdx → {real_slug}.mdx, open GitHub PR."""
    if not authorized(update): return
    preview_slug = await db_get("pending_preview_slug")
    real_slug    = await db_get("pending_real_slug")
    mdx_path     = await db_get("pending_mdx_path")

    if not preview_slug or not real_slug:
        await auth_reply(update, "No pending draft to publish. Use `/approve` on a brief first.")
        return

    import shutil
    src = Path(mdx_path)
    if not src.exists():
        await auth_reply(update, f"❌ Draft file not found: `{mdx_path}`")
        return

    articles_dir = src.parent
    dst = articles_dir / f"{real_slug}.mdx"

    # Rename preview → real slug
    src.rename(dst)

    # Clear pending state
    await db_set("pending_preview_slug", "")
    await db_set("pending_real_slug", "")
    await db_set("pending_mdx_path", "")

    await update.message.reply_text(f"✅ Renamed to `{real_slug}.mdx`. Opening GitHub PR…", parse_mode="Markdown")
    rc, out = run_agent("publisher.py", str(dst), timeout=120)
    if rc == 0:
        pr_match = re.search(r"https://github\.com/\S+/pull/\d+", out)
        pr_url = pr_match.group(0) if pr_match else None
        if pr_url:
            await update.message.reply_text(
                f"🚀 PR opened:\n{pr_url}\n\nSet `draft: false` in Keystatic then merge to publish.",
            )
        else:
            await update.message.reply_text(f"✅ Done:\n```\n{out[-600:]}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Publisher failed:\n```\n{out[-800:]}\n```", parse_mode="Markdown")


# ── /amend ───────────────────────────────────────────────────────────────────

async def cmd_amend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args:
        await auth_reply(update, "Usage: `/amend [instructions]`\nExample: `/amend too technical, reframe for general audience`")
        return

    path = await db_get("active_brief_path")
    if not path:
        await auth_reply(update, "No active brief. Use `/list` and `/pick [n]`.")
        return

    instructions = " ".join(context.args)
    await update.message.reply_text(f"🔄 Regenerating brief: _{instructions}_…", parse_mode="Markdown")
    rc, out = run_agent("brief_generator.py", "--amend", path, instructions, timeout=120)
    if rc == 0:
        content = _read_brief(path)
        await update.message.reply_text(f"📋 *Brief updated:*\n\n{content[:3000]}", parse_mode="Markdown")
        await update.message.reply_text("→ `/approve` · `/amend [notes]` · `/reject [reason]`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Amend failed:\n```\n{out[-800:]}\n```", parse_mode="Markdown")


# ── /merge ────────────────────────────────────────────────────────────────────

async def cmd_merge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if len(context.args or []) < 2 or not all(a.isdigit() for a in context.args[:2]):
        await auth_reply(update, "Usage: `/merge [n] [m]`\nMerge two pending briefs. Use `/list` to see numbers.")
        return

    briefs = get_pending_briefs()
    n, m = int(context.args[0]), int(context.args[1])
    if n < 1 or m < 1 or n > len(briefs) or m > len(briefs) or n == m:
        await auth_reply(update, f"❌ Invalid brief numbers. Use `/list` (found {len(briefs)}).")
        return

    b1, b2 = briefs[n - 1], briefs[m - 1]
    await update.message.reply_text(f"🔄 Merging briefs {n} and {m}…")
    rc, out = run_agent("brief_generator.py", "--merge", b1["path"], b2["path"], timeout=120)
    if rc == 0:
        await update.message.reply_text(f"✅ Merged brief ready:\n```\n{out[:1500]}\n```", parse_mode="Markdown")
        # Re-list pending after merge
        new_briefs = get_pending_briefs()
        if new_briefs:
            await db_set("active_brief_path", new_briefs[0]["path"])
        await update.message.reply_text("→ `/approve` · `/amend [notes]` · `/reject [reason]`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Merge failed:\n```\n{out[-800:]}\n```", parse_mode="Markdown")


# ── /reject ───────────────────────────────────────────────────────────────────

async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    path = await db_get("active_brief_path")
    if not path:
        await auth_reply(update, "No active brief. Use `/list` and `/pick [n]`.")
        return

    reason = " ".join(context.args) if context.args else "no reason given"
    brief_file = Path(path)
    day = brief_file.parent.name
    rejected_dir = REJECTED_DIR / day
    rejected_dir.mkdir(parents=True, exist_ok=True)

    # Append reason to brief before moving
    existing = brief_file.read_text(encoding="utf-8")
    brief_file.write_text(
        existing + f"\n\n## Rejected\nDate: {datetime.now().isoformat()}\nReason: {reason}\n",
        encoding="utf-8",
    )
    (rejected_dir / brief_file.name).write_text(brief_file.read_text(encoding="utf-8"), encoding="utf-8")

    slug = brief_file.stem
    await update.message.reply_text(f"🗑️ Brief _{slug}_ rejected.\nReason: {reason}", parse_mode="Markdown")
    await db_set("active_brief_path", "")

    # Auto-show next if any
    remaining = get_pending_briefs()
    if remaining:
        await update.message.reply_text(f"📋 {len(remaining)} brief(s) still pending. Use `/list`.")


# ── /ooni ─────────────────────────────────────────────────────────────────────

async def cmd_ooni(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    filter_arg = " ".join(context.args) if context.args else ""
    await update.message.reply_text("📡 Fetching OONI data…")
    rc, out = run_agent("ooni_watcher.py", "--report", filter_arg, timeout=60)
    if rc == 0:
        await update.message.reply_text(f"```\n{out[:3000]}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ OONI fetch failed:\n```\n{out[-600:]}\n```", parse_mode="Markdown")


# ── /search ──────────────────────────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args:
        await auth_reply(update, "Usage: `/search [query]`")
        return

    query = " ".join(context.args).lower()
    results = []
    if ARTICLES_DIR.exists():
        for mdx_file in ARTICLES_DIR.glob("*.mdx"):
            content = mdx_file.read_text(encoding="utf-8", errors="replace")
            if query in content.lower():
                title = _extract_title(content, mdx_file.stem)
                # Extract publishedAt
                date_match = re.search(r"publishedAt:\s*(.+)", content)
                date = date_match.group(1).strip() if date_match else "?"
                results.append({"title": title, "slug": mdx_file.stem, "date": date})

    if not results:
        await auth_reply(update, f"No articles found matching _{query}_.", )
        return

    lines = [f"🔍 *Results for \"{query}\" ({len(results)}):*\n"]
    for i, r in enumerate(results[:10], 1):
        lines.append(f"[{i}] {r['title']} — {r['date']}")
        lines.append(f"    `{r['slug']}`")
    if len(results) > 10:
        lines.append(f"\n…and {len(results) - 10} more.")
    await auth_reply(update, "\n".join(lines))


# ── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    now = datetime.now().strftime("%b %d, %Y %H:%M")

    briefs = get_pending_briefs()
    paused = await db_get("cron_paused")

    lines = [f"*Pipeline Status — {now}*\n"]

    # Cron status
    lines.append("*CRON JOBS*")
    if paused:
        resume_at = await db_get("cron_resume_at")
        lines.append(f"⏸️  Paused{f' until {resume_at}' if resume_at else ''}")
    else:
        lines.append("▶️  Running")

    for agent, log_name in [("monitor.py", "monitor"), ("ooni_watcher.py", "ooni")]:
        log_file = LOGS_DIR / f"{log_name}.log"
        if log_file.exists():
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime).strftime("%b %d %H:%M")
            lines.append(f"✅ {agent:<20} Last run: {mtime}")
        else:
            lines.append(f"⚠️  {agent:<20} No log found")

    # Pending briefs
    lines.append(f"\n*PENDING BRIEFS ({len(briefs)})*")
    if briefs:
        for i, b in enumerate(briefs[:5], 1):
            lines.append(f"📋 [{i}] {b['title']}")
        lines.append("→ `/list` for details, `/pick [n]` to select")
    else:
        lines.append("None")

    # Published articles (last 7 days)
    if ARTICLES_DIR.exists():
        week_ago = datetime.now() - timedelta(days=7)
        recent = []
        for f in ARTICLES_DIR.glob("*.mdx"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime >= week_ago:
                recent.append((mtime, f.stem))
        recent.sort(reverse=True)
        lines.append(f"\n*RECENTLY PUBLISHED (7 days)*")
        for dt, slug in recent[:5]:
            lines.append(f"✅ {slug} — {dt.strftime('%b %d')}")
        if not recent:
            lines.append("None")

    await auth_reply(update, "\n".join(lines))


# ── /run ─────────────────────────────────────────────────────────────────────

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    paused = await db_get("cron_paused")
    if paused:
        await auth_reply(update, "⏸️  Pipeline is paused. Use `/resume` first.")
        return

    target = context.args[0].lower() if context.args else "all"
    agents_to_run: list[tuple[str, list[str]]] = []

    if target in ("all", "monitor"):
        agents_to_run.append(("monitor.py", []))
    if target in ("all", "ooni"):
        agents_to_run.append(("ooni_watcher.py", []))

    if not agents_to_run:
        await auth_reply(update, f"Unknown agent: `{target}`. Use: `monitor` / `ooni` / `all`")
        return

    await update.message.reply_text(f"⏳ Running {target} pipeline…")
    for script, args in agents_to_run:
        rc, out = run_agent(script, *args, timeout=300)
        status = "✅" if rc == 0 else "❌"
        await update.message.reply_text(f"{status} {script}:\n```\n{out[-400:]}\n```", parse_mode="Markdown")

    new_briefs = get_pending_briefs()
    if new_briefs:
        await update.message.reply_text(f"📋 {len(new_briefs)} brief(s) pending. Use `/list`.")


# ── /pause & /resume ──────────────────────────────────────────────────────────

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    hours = int(context.args[0]) if context.args and context.args[0].isdigit() else 0
    await db_set("cron_paused", "1")
    if hours:
        resume_at = (datetime.now() + timedelta(hours=hours)).strftime("%b %d %H:%M")
        await db_set("cron_resume_at", resume_at)
        await auth_reply(update, f"⏸️  Cron paused for {hours}h. Auto-resume: {resume_at}\nUse `/resume` to restart early.")
    else:
        await db_set("cron_resume_at", "")
        await auth_reply(update, "⏸️  Cron paused. Use `/resume` to restart.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    await db_set("cron_paused", "")
    await db_set("cron_resume_at", "")
    await auth_reply(update, "▶️  Cron resumed. Next monitor run: tomorrow 06:30")


# ── /log ──────────────────────────────────────────────────────────────────────

async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    agent = "monitor"
    n = 20
    args = context.args or []
    if args:
        if args[0].isdigit():
            n = int(args[0])
        else:
            agent = args[0]
            if len(args) > 1 and args[1].isdigit():
                n = int(args[1])
    lines = tail_log(agent, n)
    await update.message.reply_text(f"```\n{lines[-3000:]}\n```", parse_mode="Markdown")


# ── /sources ──────────────────────────────────────────────────────────────────

async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    config_file = BASE_DIR / "config.yaml"
    if not config_file.exists():
        await auth_reply(update, "config.yaml not found.")
        return
    import yaml  # type: ignore
    try:
        config = yaml.safe_load(config_file.read_text())
        sources = config.get("sources", {})
        lines = [f"*Monitored Sources ({len(sources)}):*\n"]
        for name, url in sources.items():
            lines.append(f"• {name}: `{url}`")
        lines.append("\n→ `/run` to force a fresh fetch")
        await auth_reply(update, "\n".join(lines))
    except Exception as e:
        await auth_reply(update, f"Error reading config: {e}")


# ── /unpublish / /archive ─────────────────────────────────────────────────────

async def cmd_unpublish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args:
        await auth_reply(update, "Usage: `/unpublish [slug or url]` [optional reason]")
        return

    # First arg may be slug or URL
    slug_or_url = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    # Extract slug from URL if needed
    slug = slug_or_url.rstrip("/").split("/")[-1]

    # Find the MDX file
    mdx_file = ARTICLES_DIR / f"{slug}.mdx"
    if not mdx_file.exists():
        # Try glob
        matches = list(ARTICLES_DIR.glob(f"*{slug}*.mdx"))
        if not matches:
            await auth_reply(update, f"❌ Article not found: `{slug}`")
            return
        mdx_file = matches[0]
        slug = mdx_file.stem

    content = mdx_file.read_text(encoding="utf-8")
    now = datetime.utcnow().isoformat() + "Z"

    # Inject archived fields into frontmatter
    if "archived:" in content:
        content = re.sub(r"archived:\s*\w+", "archived: true", content)
    else:
        content = content.replace("---\n", f"---\narchived: true\narchivedAt: '{now}'\n", 1)

    if reason and "archivedReason:" not in content:
        content = content.replace("---\n", f"---\narchivedReason: '{reason}'\n", 1)

    mdx_file.write_text(content, encoding="utf-8")

    # Commit directly to main (emergency action)
    rc, out = run_agent("publisher.py", "--archive", str(mdx_file), timeout=60)
    status = "⚠️" if rc != 0 else "✅"
    msg = (
        f"{status} Article archived.\n\n"
        f"*{slug}*\nStatus: ARCHIVED\n"
        f"{'Reason: ' + reason if reason else ''}\n\n"
        f"File preserved at: `src/content/articles/{slug}.mdx`\n"
        f"Archived at: {now}\n\n"
        f"→ `/restore {slug}` to bring it back"
    )
    await auth_reply(update, msg)


# /archive is an alias for /unpublish
async def cmd_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_unpublish(update, context)


# ── /restore ──────────────────────────────────────────────────────────────────

async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not context.args:
        await auth_reply(update, "Usage: `/restore [slug]`")
        return

    slug = context.args[0].rstrip("/").split("/")[-1]
    mdx_file = ARTICLES_DIR / f"{slug}.mdx"
    if not mdx_file.exists():
        matches = list(ARTICLES_DIR.glob(f"*{slug}*.mdx"))
        if not matches:
            await auth_reply(update, f"❌ Article not found: `{slug}`")
            return
        mdx_file = matches[0]
        slug = mdx_file.stem

    content = mdx_file.read_text(encoding="utf-8")
    content = re.sub(r"\narchived:\s*true\n", "\narchived: false\n", content)
    content = re.sub(r"\narchivedAt:[^\n]+\n", "\n", content)
    content = re.sub(r"\narchivedReason:[^\n]+\n", "\n", content)
    mdx_file.write_text(content, encoding="utf-8")

    rc, out = run_agent("publisher.py", "--restore", str(mdx_file), timeout=60)
    status = "✅" if rc == 0 else "⚠️"
    await auth_reply(update, f"{status} Article restored: `{slug}`\nWill be live after next Cloudflare deploy (~90s).")


# ── /archived ─────────────────────────────────────────────────────────────────

async def cmd_archived(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if not ARTICLES_DIR.exists():
        await auth_reply(update, "No articles directory found.")
        return

    archived = []
    for mdx_file in ARTICLES_DIR.glob("*.mdx"):
        content = mdx_file.read_text(encoding="utf-8", errors="replace")
        if re.search(r"archived:\s*true", content):
            title = _extract_title(content, mdx_file.stem)
            date_match = re.search(r"archivedAt:\s*'?(.+?)'?\n", content)
            date = date_match.group(1)[:10] if date_match else "?"
            archived.append({"title": title, "slug": mdx_file.stem, "date": date})

    if not archived:
        await auth_reply(update, "No archived articles.")
        return

    lines = [f"🗂️ *Archived articles ({len(archived)}):*\n"]
    for a in archived:
        lines.append(f"• {a['title']} — {a['date']}\n  `/restore {a['slug']}`")
    await auth_reply(update, "\n".join(lines))


# ── /help ──────────────────────────────────────────────────────────────────────

HELP_FULL = """*IIM Pipeline Bot — Commands*

━━━ DISCOVERY ━━━
`/draft [url(s)] [notes]` — Turn URLs into a brief
`/topic [description]` — Bot finds sources from description
`/translate [url or text]` — Translate Burmese content
`/search [query]` — Search published articles
`/ooni [filter]` — Live OONI data (city/ISP/protocol)

━━━ BRIEF MANAGEMENT ━━━
`/list` — Show all pending briefs
`/pick [n]` — Select which brief to work on
`/show` — Re-display current brief
`/approve` — Write article → open GitHub PR
`/approve [tweaks]` — Write with small article changes
`/amend [notes]` — Rethink brief angle/sources
`/merge [n] [m]` — Combine two briefs into one
`/reject [reason]` — Discard current brief

━━━ ARTICLE MANAGEMENT ━━━
`/unpublish [slug]` — Archive article (never deleted)
`/archive [slug]` — Same as /unpublish
`/restore [slug]` — Bring archived article back online
`/archived` — List all archived articles

━━━ PIPELINE CONTROL ━━━
`/status` — Full pipeline overview
`/run` — Force daily cron now
`/run [ooni|monitor|all]` — Run specific agent
`/pause [hours]` — Pause cron jobs
`/resume` — Resume cron jobs
`/log [agent] [n]` — View last N log lines
`/sources` — Status of all monitored feeds

━━━ QUICK GUIDE ━━━
Brief angle wrong? → `/amend [what to change]`
Brief OK, small tweak? → `/approve [tweak]`
Two briefs, same story? → `/merge [n] [m]`
Not worth publishing? → `/reject [reason]`
"""

HELP_COMMANDS = {
    "draft":    "`/draft [url(s)] [notes]`\nFetch URLs → translate if Burmese → search corroborating sources → build brief.\nExample: `/draft https://netblocks.org/xyz significant?`",
    "topic":    "`/topic [description]`\nNo URL? Bot searches for sources from your description.\nExample: `/topic reports of shutdown in Chin State`",
    "translate":"`/translate [url or text]`\nTranslate Burmese content. No article created — use `/draft [url]` after.",
    "amend":    "`/amend [instructions]`\nRethink brief angle/sources/framing. Creates v2, v3… Can amend unlimited times.\nDiff from `/approve [tweaks]`: amend rethinks the BRIEF, approve fine-tunes the ARTICLE.",
    "merge":    "`/merge [n] [m]`\nCombine two pending briefs. Use `/list` first to see numbers.",
    "unpublish":"`/unpublish [slug or url]` [reason]\nTake article offline immediately. NEVER deleted — sets `archived: true` and commits to main.",
    "restore":  "`/restore [slug]`\nBring archived article back online.",
    "status":   "`/status`\nFull overview: cron jobs, pending briefs, open PRs, recently published.",
    "run":      "`/run` or `/run [ooni|monitor|all]`\nForce pipeline to run now without waiting for cron.",
    "log":      "`/log` or `/log [agent]` or `/log [agent] [n]`\nView last N lines of agent logs. Agents: monitor, ooni, bot.",
}

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    if context.args:
        cmd = context.args[0].lstrip("/")
        detail = HELP_COMMANDS.get(cmd)
        if detail:
            await auth_reply(update, f"*/{cmd}*\n\n{detail}")
        else:
            await auth_reply(update, f"No detailed help for `/{cmd}`. Try `/help` for the full list.")
    else:
        await auth_reply(update, HELP_FULL)


# ── /test ─────────────────────────────────────────────────────────────────────

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await auth_reply(update, f"✅ IIM Bot is live — {now}\nAll systems go.")


# ── Unknown command handler ───────────────────────────────────────────────────

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update): return
    await auth_reply(update, "Unknown command. Try `/help`.")


# ── Entry point ───────────────────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    await init_db()
    log.info("Bot initialized. Polling…")


def main() -> None:
    if not BOT_TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN not set in .env")
    if not ALLOWED_CHAT:
        sys.exit("TELEGRAM_CHAT_ID not set in .env")

    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    handlers = [
        ("draft",     cmd_draft),
        ("topic",     cmd_topic),
        ("translate", cmd_translate),
        ("search",    cmd_search),
        ("ooni",      cmd_ooni),
        ("list",      cmd_list),
        ("pick",      cmd_pick),
        ("show",      cmd_show),
        ("approve",   cmd_approve),
        ("publish",   cmd_publish),
        ("amend",     cmd_amend),
        ("merge",     cmd_merge),
        ("reject",    cmd_reject),
        ("status",    cmd_status),
        ("run",       cmd_run),
        ("pause",     cmd_pause),
        ("resume",    cmd_resume),
        ("log",       cmd_log),
        ("sources",   cmd_sources),
        ("unpublish", cmd_unpublish),
        ("archive",   cmd_archive),
        ("restore",   cmd_restore),
        ("archived",  cmd_archived),
        ("help",      cmd_help),
        ("test",      cmd_test),
    ]

    for cmd_name, handler in handlers:
        app.add_handler(CommandHandler(cmd_name, handler))

    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    log.info("Starting IIM bot (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    if "--test" in sys.argv:
        # Quick connectivity test — sends a message and exits
        import asyncio
        from telegram import Bot
        async def _test():
            bot = Bot(BOT_TOKEN)
            await bot.send_message(ALLOWED_CHAT, "IIM Bot is live ✓")
            print("Test message sent.")
        asyncio.run(_test())
    else:
        main()
