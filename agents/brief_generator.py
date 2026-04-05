"""
Brief Generator
---------------
Generates article briefs from monitor output or on-demand requests.

Usage:
  python brief_generator.py                        # process today's monitor output
  python brief_generator.py --dry-run              # generate without Telegram
  python brief_generator.py --manual "url [notes]" # brief from URL(s) + notes
  python brief_generator.py --topic "description"  # brief from topic (bot finds sources)
  python brief_generator.py --amend path "instr"   # regenerate existing brief
  python brief_generator.py --merge path1 path2    # merge two briefs
  python brief_generator.py --translate "text"     # translate only, no brief
"""

import json
import logging
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import anthropic
import httpx
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

AGENTS_DIR = Path(__file__).parent
CONFIG_FILE = AGENTS_DIR / "config.yaml"
CONFIG = yaml.safe_load(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

BRIEFS_DIR = AGENTS_DIR / "briefs"
MONITOR_OUTPUT = AGENTS_DIR / "monitor_output.json"

BRIEF_SYSTEM = (
    "You are a senior editorial assistant for Internet in Myanmar, "
    "an independent monitor of Myanmar's digital censorship. "
    "Output JSON only. No preamble. No markdown fences."
)

BRIEF_JSON_SPEC = (
    "Return JSON with fields: "
    "title (string), "
    "slug (lowercase hyphens max 6 words), "
    "excerpt (max 300 chars), "
    "category (one of: Censorship & Shutdowns | Telecom & Infrastructure | "
    "Digital Economy | Guides & Tools | News - Mobile | News - Broadband | News - Policy), "
    "tags (array max 5), "
    "angle (2-3 sentences on editorial focus), "
    "key_points (array of 3-5 bullet strings), "
    "sources (array of URLs), "
    "confidence (float 0-1)."
)


def _get_model(task: str) -> str:
    models = CONFIG.get("anthropic", {}).get("models", {})
    return models.get(task, "claude-sonnet-4-6")


def _get_max_tokens(task: str) -> int:
    tokens = CONFIG.get("anthropic", {}).get("max_tokens", {})
    return tokens.get(task, 800)


# ── Core brief generation ────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def generate_brief(item: dict) -> dict:
    """Turn a scored monitor item into a brief (cron path)."""
    response = CLIENT.messages.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        system=BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Create a brief for this news item:\n\n{json.dumps(item, indent=2)}\n\n"
                + BRIEF_JSON_SPEC
            ),
        }],
    )
    return json.loads(response.content[0].text)


def _save_brief(brief: dict) -> Path:
    today = date.today().isoformat()
    out_dir = BRIEFS_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = brief.get("slug", str(uuid.uuid4())[:8])
    brief_path = out_dir / f"{slug}.md"
    # Write as markdown with frontmatter-style header
    lines = [
        f"# {brief.get('title', slug)}\n",
        f"**Slug:** `{slug}`\n",
        f"**Category:** {brief.get('category', '')}\n",
        f"**Confidence:** {brief.get('confidence', '?')}\n",
        f"**Tags:** {', '.join(brief.get('tags', []))}\n\n",
        f"## Angle\n{brief.get('angle', '')}\n\n",
        "## Key Points\n",
    ]
    for pt in brief.get("key_points", []):
        lines.append(f"- {pt}\n")
    lines.append(f"\n## Excerpt\n{brief.get('excerpt', '')}\n\n")
    lines.append("## Sources\n")
    for src in brief.get("sources", []):
        lines.append(f"- {src}\n")
    brief_path.write_text("".join(lines), encoding="utf-8")
    log.info(f"Brief saved: {brief_path}")
    return brief_path


# ── URL fetching ──────────────────────────────────────────────────────────────

def _fetch_url(url: str) -> str:
    """Fetch URL and return clean text (max 5000 chars)."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; IIM-bot/1.0)"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            # Remove nav/footer/ads
            for tag in soup(["nav", "footer", "script", "style", "aside"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)[:5000]
    except Exception as e:
        log.warning(f"Could not fetch {url}: {e}")
        return ""


def _extract_urls(text: str) -> tuple[list[str], str]:
    """Split space-separated URLs from notes text."""
    import re
    urls = re.findall(r'https?://\S+', text)
    notes = re.sub(r'https?://\S+', '', text).strip()
    return urls, notes


# ── --manual mode ─────────────────────────────────────────────────────────────

def cmd_manual(args_text: str) -> None:
    """Create brief from URL(s) + optional notes."""
    urls, notes = _extract_urls(args_text)
    if not urls:
        print("No URLs found in arguments.", file=sys.stderr)
        sys.exit(1)

    fetched = []
    for url in urls:
        content = _fetch_url(url)
        if content:
            fetched.append({"url": url, "content": content})
        else:
            fetched.append({"url": url, "content": "(fetch failed)"})

    combined = "\n\n".join(
        f"SOURCE: {f['url']}\n{f['content'][:2000]}" for f in fetched
    )
    if notes:
        combined = f"EDITOR NOTES: {notes}\n\n" + combined

    response = CLIENT.messages.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        system=BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                "Create an article brief for Internet in Myanmar from these sources.\n\n"
                f"{combined}\n\n"
                + BRIEF_JSON_SPEC
            ),
        }],
    )
    brief = json.loads(response.content[0].text)
    path = _save_brief(brief)
    print(f"Brief saved: {path}", file=sys.stderr)


# ── --topic mode ──────────────────────────────────────────────────────────────

def cmd_topic(topic: str) -> None:
    """Bot searches for sources from description, then builds brief."""
    # Try Tavily search if available, else use Claude directly
    sources_text = ""
    try:
        from utils.model_router import search
        results = search(topic, max_results=5, trusted_only=True)
        if results:
            sources_text = "\n\n".join(
                f"SOURCE: {r['url']}\n{r.get('content', '')[:1500]}"
                for r in results
            )
            log.info(f"Found {len(results)} sources via Tavily")
    except Exception as e:
        log.warning(f"Tavily search unavailable: {e}")

    prompt_content = f"TOPIC: {topic}\n\n"
    if sources_text:
        prompt_content += f"SOURCES FOUND:\n{sources_text}\n\n"
    else:
        prompt_content += "(No sources fetched — generate brief based on topic knowledge)\n\n"

    response = CLIENT.messages.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        system=BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                "Create an article brief for Internet in Myanmar on this topic.\n\n"
                + prompt_content
                + BRIEF_JSON_SPEC
                + "\nIf sources are insufficient, set confidence below 0.5 and note in angle."
            ),
        }],
    )
    brief = json.loads(response.content[0].text)
    path = _save_brief(brief)
    print(f"Brief saved: {path}", file=sys.stderr)


# ── --amend mode ──────────────────────────────────────────────────────────────

def cmd_amend(brief_path: str, instructions: str) -> None:
    """Regenerate brief with new angle/instructions."""
    path = Path(brief_path)
    if not path.exists():
        print(f"Brief not found: {brief_path}", file=sys.stderr)
        sys.exit(1)

    original = path.read_text(encoding="utf-8")
    response = CLIENT.messages.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        system=BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                "Regenerate this brief with the following instructions. "
                "Keep all original sources. Change angle/framing/structure as instructed.\n\n"
                f"INSTRUCTIONS: {instructions}\n\n"
                f"ORIGINAL BRIEF:\n{original}\n\n"
                + BRIEF_JSON_SPEC
            ),
        }],
    )
    brief = json.loads(response.content[0].text)
    # Overwrite in place (versioning via git history)
    new_path = _save_brief(brief)
    # Also overwrite original path to keep active_brief_path valid
    path.write_text(new_path.read_text(encoding="utf-8"), encoding="utf-8")
    log.info(f"Brief amended: {path}")
    print(f"Brief amended: {path}", file=sys.stderr)


# ── --merge mode ──────────────────────────────────────────────────────────────

def cmd_merge(path1: str, path2: str) -> None:
    """Merge two briefs into one."""
    p1, p2 = Path(path1), Path(path2)
    if not p1.exists() or not p2.exists():
        print("One or both brief files not found.", file=sys.stderr)
        sys.exit(1)

    b1 = p1.read_text(encoding="utf-8")
    b2 = p2.read_text(encoding="utf-8")

    response = CLIENT.messages.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        system=BRIEF_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                "Merge these two briefs into one stronger brief. "
                "Combine all sources. Improve angle and coverage. "
                "The merged article should be richer than either alone.\n\n"
                f"BRIEF 1:\n{b1}\n\nBRIEF 2:\n{b2}\n\n"
                + BRIEF_JSON_SPEC
            ),
        }],
    )
    brief = json.loads(response.content[0].text)
    merged_path = _save_brief(brief)
    # Remove the two originals from pending (rename with .merged suffix)
    p1.rename(p1.with_suffix(".merged"))
    p2.rename(p2.with_suffix(".merged"))
    print(f"Merged brief saved: {merged_path}", file=sys.stderr)


# ── --translate mode ──────────────────────────────────────────────────────────

def cmd_translate(text_or_url: str) -> None:
    """Translate Burmese content. No brief generated."""
    content = text_or_url
    source_url = None

    if text_or_url.startswith("http"):
        source_url = text_or_url
        content = _fetch_url(text_or_url)
        if not content:
            print("Could not fetch URL.", file=sys.stderr)
            sys.exit(1)

    # Check sensitivity for routing
    from utils.model_router import is_sensitive, call as model_call
    meta = {"telegram_origin": False, "has_names": False}

    if is_sensitive(content, meta):
        result = model_call("translate_mm", "Translate this Myanmar (Burmese) text to English. Key facts only. Transliterate names.", content[:4000])
    else:
        # Safe to use Qwen for neutral content
        result = model_call("translate_mm", "Translate this Myanmar (Burmese) text to English. Key facts only. Transliterate names.", content[:4000])

    output = f"Translation:\n\n{result}"
    if source_url:
        output += f"\n\nSource: {source_url}"
        output += f"\n\n→ Use /draft {source_url} to create an article from this."
    print(output)


# ── Cron path ─────────────────────────────────────────────────────────────────

def run(dry_run: bool = False):
    if not MONITOR_OUTPUT.exists():
        log.error("monitor_output.json not found — run monitor.py first")
        sys.exit(1)

    items = json.loads(MONITOR_OUTPUT.read_text())
    min_score = CONFIG.get("scoring", {}).get("min_score_for_brief", 6.0)
    eligible = [i for i in items if i.get("score", 0) >= min_score]

    log.info(f"{len(eligible)} items above score threshold {min_score}")

    for item in eligible:
        try:
            brief = generate_brief(item)
            brief["id"] = str(uuid.uuid4())
            _save_brief(brief)
        except Exception as e:
            log.error(f"Failed for item {item.get('title', '?')}: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--manual" in args:
        idx = args.index("--manual")
        arg_text = args[idx + 1] if len(args) > idx + 1 else ""
        cmd_manual(arg_text)

    elif "--topic" in args:
        idx = args.index("--topic")
        topic = args[idx + 1] if len(args) > idx + 1 else ""
        cmd_topic(topic)

    elif "--amend" in args:
        idx = args.index("--amend")
        path = args[idx + 1] if len(args) > idx + 1 else ""
        instr = args[idx + 2] if len(args) > idx + 2 else ""
        cmd_amend(path, instr)

    elif "--merge" in args:
        idx = args.index("--merge")
        p1 = args[idx + 1] if len(args) > idx + 1 else ""
        p2 = args[idx + 2] if len(args) > idx + 2 else ""
        cmd_merge(p1, p2)

    elif "--translate" in args:
        idx = args.index("--translate")
        text = args[idx + 1] if len(args) > idx + 1 else ""
        cmd_translate(text)

    else:
        run(dry_run="--dry-run" in args)
