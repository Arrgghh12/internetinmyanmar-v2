"""
Telegram alert helper for background agents (bgp_monitor, ooni_watcher, etc.)
Sends a message to the configured chat. Silently logs if env vars are missing.
"""

import logging
import os

log = logging.getLogger(__name__)


async def send_alert(message: str) -> None:
    """Send a Markdown-formatted alert to the IIM Telegram chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.warning("[TELEGRAM DISABLED] %s", message[:120])
        return

    try:
        from telegram import Bot
        async with Bot(token) as bot:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
            )
    except Exception as e:
        log.error("Telegram send failed: %s", e)
