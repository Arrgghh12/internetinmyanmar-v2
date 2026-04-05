"""
Article Writer
--------------
Generates a full MDX article from an approved brief.
Called by the Telegram bot after Anna approves or adjusts a brief.

Usage:
  python writer.py --brief-id <uuid>
  python writer.py --brief-id <uuid> --adjustments "focus more on telecom impact"

Output: JSON to stdout → {"path": "/path/to/article.mdx"}
"""

import json
import logging
import os
import sys
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
ARTICLES_DIR = Path(CONFIG["paths"]["articles"]).expanduser()


def find_brief(brief_id: str) -> dict:
    for f in BRIEFS_DIR.rglob("*.json"):
        data = json.loads(f.read_text())
        if data.get("id") == brief_id:
            return data
    raise FileNotFoundError(f"Brief {brief_id} not found")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def write_article(brief: dict, adjustments: str = "") -> str:
    """Generate full MDX content from brief via Claude."""
    adj_note = f"\n\nEditor adjustments to incorporate:\n{adjustments}" if adjustments else ""

    response = CLIENT.messages.create(
        model=CONFIG["anthropic"]["models"]["write"],
        max_tokens=CONFIG["anthropic"]["max_tokens"]["write"],
        system=(
            "You are writing for Internet in Myanmar, an independent monitor of Myanmar's "
            "digital censorship. Author: Anna Faure Revol. Tone: precise, analytical, "
            "never sensationalist. Credible to OONI, Citizen Lab, RSF, Freedom House.\n\n"
            "Output the article body only — no frontmatter, no fences. "
            "Use markdown headings (## for H2, ### for H3). "
            f"Target {CONFIG['article']['target_words'][0]}–{CONFIG['article']['target_words'][1]} words. "
            f"Include {CONFIG['article']['internal_links'][0]}–{CONFIG['article']['internal_links'][1]} "
            "internal links using descriptive anchor text. "
            "No keyword stuffing. No sensationalism."
        ),
        messages=[{
            "role": "user",
            "content": f"Write the article from this brief:\n\n{json.dumps(brief, indent=2)}{adj_note}",
        }],
    )
    return response.content[0].text


def build_frontmatter(brief: dict) -> str:
    today = date.today().isoformat()
    tags_yaml = "\n".join(f"  - {t}" for t in brief.get("tags", []))
    sources_yaml = "\n".join(f"  - {s}" for s in brief.get("sources", []))
    return f"""---
title: "{brief['title']}"
seoTitle: "{brief['title'][:60]}"
metaDescription: "{brief.get('excerpt', '')[:155]}"
slug: "{brief['slug']}"
category: "{brief['category']}"
tags:
{tags_yaml}
author: "Anna Faure Revol"
publishedAt: {today}
draft: true
excerpt: "{brief.get('excerpt', '')[:300]}"
lang: "en"
sources:
{sources_yaml}
---

"""


def run(brief_id: str, adjustments: str = ""):
    brief = find_brief(brief_id)
    body = write_article(brief, adjustments)
    frontmatter = build_frontmatter(brief)
    content = frontmatter + body

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTICLES_DIR / f"{brief['slug']}.mdx"
    out_path.write_text(content, encoding="utf-8")

    # Also write a plain .txt for Telegram (easier to read on mobile)
    txt_path = AGENTS_DIR / "drafts" / f"{brief['slug']}.txt"
    txt_path.parent.mkdir(exist_ok=True)
    txt_path.write_text(content, encoding="utf-8")

    print(json.dumps({"path": str(txt_path), "mdx_path": str(out_path)}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = sys.argv[1:]
    bid = args[args.index("--brief-id") + 1] if "--brief-id" in args else None
    adj = args[args.index("--adjustments") + 1] if "--adjustments" in args else ""
    if not bid:
        print("Usage: writer.py --brief-id <id> [--adjustments '...']", file=sys.stderr)
        sys.exit(1)
    run(bid, adj)
