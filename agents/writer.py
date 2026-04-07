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
import uuid
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
    "First character of your response = first character of the article body.\n\n"
    "CRITICAL — SOURCE LINKS:\n"
    "When you mention external organizations or reports inline, embed a real hyperlink using markdown: "
    "[anchor text](URL). Only use URLs you are certain exist. Prefer top-level or well-known "
    "section URLs (e.g. https://explorer.ooni.org/country/MM, https://rsf.org/en/myanmar, "
    "https://freedomhouse.org/country/myanmar/freedom-net/2025, "
    "https://citizenlab.ca/tag/myanmar/, https://www.accessnow.org/issue/internet-shutdowns/). "
    "NEVER invent URL paths. If unsure of the exact URL, use only the root domain "
    "(e.g. https://rsf.org) or omit the link entirely. A missing link is better than a 404."
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
            brief["slug"] = re.sub(r'[`* ]', '', line.split(":", 1)[1]).strip()
        elif line.lower().startswith("**category:**"):
            brief["category"] = re.sub(r'[`*]', '', line.split(":", 1)[1]).strip()
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


def write_article(brief_text: str, adjustments: str = "", force_deepseek: bool = False) -> str:
    """Always use DeepSeek-V3. Claude routing disabled until API credits confirmed."""
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


SITE_URL = os.getenv("SITE_URL", "https://dev.internetinmyanmar.com")


def run(brief_path: str, adjustments: str = "", force_deepseek: bool = False) -> dict:
    brief, raw_text = _read_brief(brief_path)
    log.info(f"Writing article for: {brief.get('title', brief_path)}")

    body = write_article(raw_text, adjustments, force_deepseek=force_deepseek)
    frontmatter = build_frontmatter(brief)
    full_content = frontmatter + body

    real_slug = brief.get("slug", "article")

    # Save under a random preview token — accessible at /preview/{token}
    # On approval, publisher renames to real SEO slug
    token = uuid.uuid4().hex[:16]
    preview_slug = f"preview-{token}"

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    mdx_path = ARTICLES_DIR / f"{preview_slug}.mdx"
    mdx_path.write_text(full_content, encoding="utf-8")

    preview_url = f"{SITE_URL}/preview/{token}/"

    # Push to git so Cloudflare builds the preview
    _git_push_preview(mdx_path, preview_slug)

    result = {
        "preview_url": preview_url,
        "preview_slug": preview_slug,
        "real_slug": real_slug,
        "mdx_path": str(mdx_path),
    }
    print(json.dumps(result))
    log.info(f"Article written (preview): {mdx_path}")
    log.info(f"Preview URL: {preview_url}")
    return result


def _git_push_preview(mdx_path: Path, preview_slug: str) -> None:
    """Commit and push the preview MDX so Cloudflare builds it."""
    import subprocess
    repo = mdx_path.parent
    while repo != repo.parent:
        if (repo / ".git").exists():
            break
        repo = repo.parent
    if not (repo / ".git").exists():
        log.warning("git push: could not find repo root")
        return
    try:
        subprocess.run(["git", "-C", str(repo), "add", str(mdx_path)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", f"draft: {preview_slug}"],
            check=True,
        )
        subprocess.run(["git", "-C", str(repo), "push"], check=True)
        log.info(f"Preview pushed to git → Cloudflare will build {preview_slug}")
    except Exception as e:
        log.warning(f"git push preview failed: {e}")


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
        print("Usage: writer.py /path/to/brief.md [--adjustments '...'] [--deepseek]", file=sys.stderr)
        sys.exit(1)
    adj = args[args.index("--adjustments") + 1] if "--adjustments" in args else ""
    force_ds = "--deepseek" in args
    run(brief_path, adj, force_deepseek=force_ds)
