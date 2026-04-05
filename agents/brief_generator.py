"""
Brief Generator
---------------
Reads scored items from monitor.py output, generates article briefs
via Claude, saves them to agents/briefs/YYYY-MM-DD/, and sends each
one to Anna via Telegram.

Usage:
  python brief_generator.py                   # process today's monitor output
  python brief_generator.py --dry-run         # generate without sending to Telegram
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
log = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent
CONFIG = yaml.safe_load((AGENTS_DIR / "config.yaml").read_text())
CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

BRIEFS_DIR = AGENTS_DIR / "briefs"
MONITOR_OUTPUT = AGENTS_DIR / "monitor_output.json"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def generate_brief(item: dict) -> dict:
    """Call Claude to turn a scored monitor item into a structured brief."""
    response = CLIENT.messages.create(
        model=CONFIG["anthropic"]["models"]["brief"],
        max_tokens=CONFIG["anthropic"]["max_tokens"]["brief"],
        system=(
            "You are a senior editorial assistant for Internet in Myanmar, "
            "an independent monitor of Myanmar's digital censorship. "
            "Output JSON only. No preamble."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Create a brief for this news item:\n\n{json.dumps(item, indent=2)}\n\n"
                "Return JSON with fields: title, slug, excerpt (max 300 chars), "
                "category (one of: Censorship & Shutdowns | Telecom & Infrastructure | "
                "Digital Economy | Guides & Tools | News - Mobile | News - Broadband | News - Policy), "
                "tags (array, max 5), angle (2-3 sentences on editorial focus), "
                "key_points (array of 3-5 bullet strings), sources (array of URLs from item)."
            ),
        }],
    )
    return json.loads(response.content[0].text)


async def send_to_telegram(brief: dict):
    from telegram_bot import send_brief
    await send_brief(brief)


def run(dry_run: bool = False):
    if not MONITOR_OUTPUT.exists():
        log.error("monitor_output.json not found — run monitor.py first")
        sys.exit(1)

    items = json.loads(MONITOR_OUTPUT.read_text())
    min_score = CONFIG["scoring"]["min_score_for_brief"]
    eligible = [i for i in items if i.get("score", 0) >= min_score]

    log.info(f"{len(eligible)} items above score threshold {min_score}")

    today = date.today().isoformat()
    out_dir = BRIEFS_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    for item in eligible:
        try:
            brief = generate_brief(item)
            brief["id"] = str(uuid.uuid4())
            brief_path = out_dir / f"{brief['slug']}.json"
            brief["path"] = str(brief_path)
            brief_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False))
            log.info(f"Brief saved: {brief['slug']}")

            if not dry_run:
                asyncio.run(send_to_telegram(brief))
                log.info(f"Sent to Telegram: {brief['title']}")

        except Exception as e:
            log.error(f"Failed for item {item.get('title', '?')}: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(dry_run="--dry-run" in sys.argv)
