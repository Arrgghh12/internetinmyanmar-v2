"""
Article Writer
--------------
Generates a full MDX article from an approved brief.
Uses DeepSeek-V3 (no Anthropic credits) for non-sensitive content,
Claude Sonnet for sensitive content (China-related, named individuals).

Usage:
  python writer.py /path/to/brief.md [--adjustments "focus more on telecom impact"]
  python writer.py --brief-id <uuid> [--adjustments "..."]  (legacy)
"""

import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

AGENTS_DIR = Path(__file__).parent
CONFIG_FILE = AGENTS_DIR / "config.yaml"
CONFIG = yaml.safe_load(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

BRIEFS_DIR   = AGENTS_DIR / "briefs"
APPROVED_DIR = AGENTS_DIR / "approved"
ARTICLES_DIR = Path(CONFIG.get("paths", {}).get("articles", "~/dev/iimv2/src/content/articles")).expanduser()

SYSTEM_PROMPT = (
    "You are writing for Internet in Myanmar, an independent monitor of Myanmar's "
    "digital censorship and internet freedom. Author: Anna Faure Revol. "
    "Tone: precise, analytical, never sensationalist. "
    "Credible to technical audiences (OONI, Citizen Lab) and institutional ones (RSF, Freedom House).\n\n"
    "Output the article body ONLY — no frontmatter, no markdown code fences. "
    "Use ## for H2 headings, ### for H3. "
    "Target 1200–1800 words. "
    "Include 3–5 internal links with descriptive anchor text. "
    "No keyword stuffing. No sensationalism. "
    "First character of your response = first character of the article body."
)


def _read_brief(path: str) -> tuple[dict, str]:
    """Read a brief file (.md or .json). Returns (parsed_dict, raw_text)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Brief not found: {path}")
    raw = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        return json.loads(raw), raw
    # Parse markdown brief into dict
    brief = {"raw": raw, "sources": []}
    for line in raw.splitlines():
        if line.startswith("# "):
            brief["title"] = line[2:].strip()
        elif line.lower().startswith("**slug:**"):
            brief["slug"] = re.sub(r'`', '', line.split(":", 1)[1]).strip()
        elif line.lower().startswith("**category:**"):
            brief["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("- http"):
            brief["sources"].append(line[2:].strip())
    if "slug" not in brief:
        brief["slug"] = re.sub(r"[^a-z0-9]+", "-", brief.get("title", "article").lower()).strip("-")[:60]
    if "category" not in brief:
        brief["category"] = "News - Policy"
    return brief, raw


def _write_with_deepseek(brief_text: str, adjustments: str) -> str:
    """Use DeepSeek-V3 directly (cheap, no Anthropic credits)."""
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )
    adj_note = f"\n\nEditor adjustments: {adjustments}" if adjustments else ""
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Write the article from this brief:\n\n{brief_text}{adj_note}"},
        ],
        max_tokens=3000,
        temperature=0.7,
    )
    return resp.choices[0].message.content


def _write_with_claude(brief_text: str, adjustments: str) -> str:
    """Use Claude Sonnet for sensitive content (China, named individuals)."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    adj_note = f"\n\nEditor adjustments: {adjustments}" if adjustments else ""
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Write the article from this brief:\n\n{brief_text}{adj_note}"}],
    )
    return resp.content[0].text


def write_article(brief_text: str, adjustments: str = "") -> str:
    """Route to correct model based on content sensitivity."""
    sys.path.insert(0, str(AGENTS_DIR))
    try:
        from utils.model_router import is_sensitive
        if is_sensitive(brief_text):
            log.info("Sensitive content detected — using Claude Sonnet")
            return _write_with_claude(brief_text, adjustments)
    except ImportError:
        pass
    log.info("Using DeepSeek-V3 for article generation")
    return _write_with_deepseek(brief_text, adjustments)


def build_frontmatter(brief: dict) -> str:
    today = date.today().isoformat()
    title = brief.get("title", "Untitled").replace('"', "'")
    seo_title = title[:57] + "…" if len(title) > 60 else title
    slug = brief.get("slug", "article")
    category = brief.get("category", "News - Policy")
    tags = brief.get("tags", [])
    sources = brief.get("sources", [])
    excerpt = brief.get("excerpt", brief.get("angle", ""))[:280].replace('"', "'")

    tags_str = json.dumps(tags)
    sources_yaml = "\n".join(f"  - \"{s}\"" for s in sources if s.startswith("http"))

    return f"""---
title: "{title}"
seoTitle: "{seo_title}"
metaDescription: "{excerpt[:152]}{'…' if len(excerpt) > 152 else ''}"
category: "{category}"
tags: {tags_str}
author: "Anna Faure Revol"
publishedAt: {today}
draft: true
excerpt: "{excerpt}"
lang: "en"
sources:
{sources_yaml or '  []'}
---

"""


def run(brief_path: str, adjustments: str = "") -> dict:
    brief, raw_text = _read_brief(brief_path)
    log.info(f"Writing article for: {brief.get('title', brief_path)}")

    body = write_article(raw_text, adjustments)
    frontmatter = build_frontmatter(brief)
    full_content = frontmatter + body

    slug = brief.get("slug", "article")
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    mdx_path = ARTICLES_DIR / f"{slug}.mdx"
    mdx_path.write_text(full_content, encoding="utf-8")

    # Plain .txt for easy Telegram reading
    drafts_dir = AGENTS_DIR / "drafts"
    drafts_dir.mkdir(exist_ok=True)
    txt_path = drafts_dir / f"{slug}.txt"
    txt_path.write_text(full_content, encoding="utf-8")

    result = {"path": str(txt_path), "mdx_path": str(mdx_path), "slug": slug}
    print(json.dumps(result))
    log.info(f"Article written: {mdx_path}")
    return result


if __name__ == "__main__":
    args = sys.argv[1:]

    # Legacy: --brief-id <uuid>
    if "--brief-id" in args:
        bid = args[args.index("--brief-id") + 1]
        adj = args[args.index("--adjustments") + 1] if "--adjustments" in args else ""
        # Find brief by ID
        for f in BRIEFS_DIR.rglob("*.json"):
            d = json.loads(f.read_text())
            if d.get("id") == bid:
                run(str(f), adj)
                sys.exit(0)
        print(f"Brief {bid} not found", file=sys.stderr)
        sys.exit(1)

    # New: positional path argument
    brief_path = args[0] if args and not args[0].startswith("--") else None
    if not brief_path:
        print("Usage: writer.py /path/to/brief.md [--adjustments '...']", file=sys.stderr)
        sys.exit(1)
    adj = args[args.index("--adjustments") + 1] if "--adjustments" in args else ""
    run(brief_path, adj)
