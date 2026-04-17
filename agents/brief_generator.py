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
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv(Path(__file__).parent / ".env")
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

AGENTS_DIR = Path(__file__).parent
CONFIG_FILE = AGENTS_DIR / "config.yaml"
CONFIG = yaml.safe_load(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
CLIENT = OpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
)

BRIEFS_DIR = AGENTS_DIR / "briefs"
MONITOR_OUTPUT = AGENTS_DIR / "monitor_output.json"
ARTICLES_DIR = AGENTS_DIR.parent / "src" / "content" / "articles"

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


# ── Coverage deduplication ────────────────────────────────────────────────────

def _build_coverage_index(days: int = 30) -> list[dict]:
    """
    Return a compact list of recent coverage: briefs from the last N days
    and all published articles. Each entry: {title, excerpt, source}.
    """
    index = []
    cutoff = date.today() - timedelta(days=days)

    # Recent briefs (scan YYYY-MM-DD subdirs within window)
    if BRIEFS_DIR.exists():
        for day_dir in sorted(BRIEFS_DIR.iterdir()):
            if not day_dir.is_dir():
                continue
            try:
                dir_date = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if dir_date < cutoff:
                continue
            for brief_file in day_dir.glob("*.md"):
                text = brief_file.read_text(encoding="utf-8")
                title_match = re.search(r'^# (.+)', text, re.MULTILINE)
                excerpt_match = re.search(r'## Excerpt\n(.+?)(?=\n##|\Z)', text, re.DOTALL)
                if title_match:
                    index.append({
                        "title": title_match.group(1).strip(),
                        "excerpt": (excerpt_match.group(1).strip()[:200] if excerpt_match else ""),
                        "source": f"brief:{brief_file.name}",
                        "date": day_dir.name,
                    })

    # Published articles (all .mdx files — read frontmatter title + excerpt)
    if ARTICLES_DIR.exists():
        for mdx in ARTICLES_DIR.glob("*.mdx"):
            text = mdx.read_text(encoding="utf-8")
            fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
            if not fm_match:
                continue
            fm_text = fm_match.group(1)
            title_match = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
            excerpt_match = re.search(r'^excerpt:\s*["\'](.+?)["\']', fm_text, re.MULTILINE)
            draft_match = re.search(r'^draft:\s*(true|false)', fm_text, re.MULTILINE)
            if title_match and (not draft_match or draft_match.group(1) == "false"):
                index.append({
                    "title": title_match.group(1).strip(),
                    "excerpt": (excerpt_match.group(1).strip()[:200] if excerpt_match else ""),
                    "source": f"article:{mdx.stem}",
                    "date": "published",
                })

    return index


def _check_overlap(item_title: str, item_summary: str, coverage_index: list[dict]) -> dict:
    """
    Ask Groq whether this item duplicates existing coverage.
    Returns {"verdict": "DUPLICATE"|"NEW_DEVELOPMENT"|"UNIQUE", "reason": str, "related": str|None}
    """
    if not coverage_index:
        return {"verdict": "UNIQUE", "reason": "no prior coverage", "related": None}

    from utils.model_router import call as model_call

    # Compact coverage list for the prompt
    coverage_lines = "\n".join(
        f"- [{e['date']}] {e['title']} | {e['excerpt'][:100]}"
        for e in coverage_index[:40]  # cap at 40 to stay within token budget
    )

    prompt = (
        "You are a deduplication filter for a Myanmar internet freedom news site.\n\n"
        "NEW ITEM:\n"
        f"Title: {item_title}\n"
        f"Summary: {item_summary[:300]}\n\n"
        "RECENT COVERAGE (briefs + published articles):\n"
        f"{coverage_lines}\n\n"
        "Is the new item:\n"
        "A) DUPLICATE — same story, no new facts (another outlet covering what we already covered)\n"
        "B) NEW_DEVELOPMENT — same ongoing story but with genuinely new information or escalation\n"
        "C) UNIQUE — distinct topic not covered before\n\n"
        "JSON only: {\"verdict\": \"DUPLICATE\"|\"NEW_DEVELOPMENT\"|\"UNIQUE\", "
        "\"reason\": \"one sentence\", \"related\": \"title of most similar piece or null\"}"
    )

    try:
        result = model_call("classify", prompt, max_tokens=120)
        return json.loads(result)
    except Exception as e:
        log.warning(f"Overlap check failed: {e} — treating as UNIQUE")
        return {"verdict": "UNIQUE", "reason": "check failed", "related": None}


def _get_model(task: str) -> str:
    return "deepseek-chat"


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text.strip())


def _get_max_tokens(task: str) -> int:
    tokens = CONFIG.get("models", {}).get("max_tokens", {})
    return tokens.get(task, 800)


def _days_old(item: dict) -> float:
    """Return how many days old this item is. None published → 999."""
    pub = item.get("published")
    if not pub:
        return 999.0
    try:
        from datetime import timezone as _tz
        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        return (datetime.now(_tz.utc) - pub_dt).total_seconds() / 86400
    except Exception:
        return 999.0


def _cluster_items(items: list[dict]) -> list[list[dict]]:
    """
    Group items by topic. Returns a list of clusters (each is a list of items).
    Uses DeepSeek to find groups; falls back to one-item clusters on failure.
    Items older than SOLO_MAX_AGE_DAYS only appear if in a multi-source cluster
    that also contains a recent item.
    """
    SOLO_MAX_AGE_DAYS = 30   # solo brief only if published within this window
    CLUSTER_MAX_AGE_DAYS = 180  # can be in cluster even if older

    if not items:
        return []

    # Build compact index for clustering prompt
    index_lines = "\n".join(
        f"{i}: {it.get('title', '')[:100]} [{it.get('source','')}]"
        for i, it in enumerate(items)
    )

    prompt = (
        "You are grouping Myanmar internet-freedom news items by topic.\n\n"
        "Rules:\n"
        "- Items about the SAME specific event/story go in the same group\n"
        "- Items about DIFFERENT aspects of a broad theme (e.g. VPN law vs VPN usage) are separate groups\n"
        "- Each item appears in exactly one group\n"
        "- Singletons (no related items) are their own group\n\n"
        "Items:\n"
        f"{index_lines}\n\n"
        "Return JSON array of arrays of integers (item indices), e.g. [[0,3,7],[1],[2,5]].\n"
        "JSON only, no preamble."
    )

    try:
        response = CLIENT.chat.completions.create(
            model=_get_model("brief"),
            max_tokens=600,
            messages=[
                {"role": "system", "content": "Output JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        groups = _parse_json(response.choices[0].message.content)
        if not isinstance(groups, list):
            raise ValueError("not a list")

        # Validate and build clusters
        seen = set()
        clusters = []
        for group in groups:
            if not isinstance(group, list):
                continue
            cluster = []
            for idx in group:
                if isinstance(idx, int) and 0 <= idx < len(items) and idx not in seen:
                    seen.add(idx)
                    cluster.append(items[idx])
            if cluster:
                clusters.append(cluster)

        # Add any items missed by the LLM
        for i, item in enumerate(items):
            if i not in seen:
                clusters.append([item])

    except Exception as e:
        log.warning(f"Clustering failed ({e}) — one brief per item")
        clusters = [[item] for item in items]

    # Filter: drop clusters where all items are old (no recent anchor)
    fresh_clusters = []
    for cluster in clusters:
        has_recent = any(_days_old(it) <= SOLO_MAX_AGE_DAYS for it in cluster)
        multi_source = len(cluster) > 1
        if has_recent or (multi_source and any(_days_old(it) <= CLUSTER_MAX_AGE_DAYS for it in cluster)):
            fresh_clusters.append(cluster)
        else:
            titles = [it.get("title", "")[:50] for it in cluster]
            log.info(f"SKIP (too old, no recent anchor): {titles}")

    log.info(f"Clustered {len(items)} items → {len(fresh_clusters)} briefs "
             f"({sum(len(c) for c in fresh_clusters if len(c)>1)} items aggregated)")
    return fresh_clusters


# ── Core brief generation ────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def generate_brief_from_cluster(cluster: list[dict], prior_coverage: str | None = None) -> dict:
    """Generate one brief from one or more related items."""
    prior_note = (
        f"\nNOTE: NEW DEVELOPMENT on an existing story. Prior coverage: '{prior_coverage}'. "
        "Focus on what is genuinely new.\n"
        if prior_coverage else ""
    )

    if len(cluster) == 1:
        clean = {k: v for k, v in cluster[0].items() if not k.startswith("_")}
        user_content = f"Create a brief for this news item:\n\n{json.dumps(clean, indent=2)}\n\n{prior_note}{BRIEF_JSON_SPEC}"
    else:
        # Multi-source: cap at 8 sources (pick highest-scored) to stay within token budget
        top = sorted(cluster, key=lambda x: x.get("score", 0), reverse=True)[:8]
        sources_digest = "\n\n".join(
            f"SOURCE {i+1} [{it.get('source','')}]:\n"
            f"Title: {it.get('title','')}\n"
            f"Published: {it.get('published','unknown')}\n"
            f"Summary: {it.get('summary','')[:300]}"
            for i, it in enumerate(top)
        )
        user_content = (
            f"Multiple sources cover the same topic. Synthesize them into ONE powerful brief "
            f"citing all {len(top)} sources (out of {len(cluster)} found).\n\n"
            f"{sources_digest}\n\n{prior_note}{BRIEF_JSON_SPEC}"
        )

    response = CLIENT.chat.completions.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        messages=[
            {"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )
    return _parse_json(response.choices[0].message.content)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def generate_brief(item: dict) -> dict:
    """Turn a scored monitor item into a brief (cron path)."""
    prior = item.get("_prior_coverage")
    development_note = (
        f"\nNOTE: This is a NEW DEVELOPMENT on an ongoing story. "
        f"Our most recent related coverage: '{prior}'. "
        "The brief angle must focus on what is genuinely new — do not repeat what was already covered.\n"
        if prior else ""
    )
    # Remove internal keys before sending to LLM
    clean_item = {k: v for k, v in item.items() if not k.startswith("_")}
    response = CLIENT.chat.completions.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        messages=[{"role": "system", "content": BRIEF_SYSTEM}, {
            "role": "user",
            "content": (
                f"Create a brief for this news item:\n\n{json.dumps(clean_item, indent=2)}\n\n"
                + development_note
                + BRIEF_JSON_SPEC
            ),
        }],
    )
    return _parse_json(response.choices[0].message.content)


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

    response = CLIENT.chat.completions.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        messages=[{"role": "system", "content": BRIEF_SYSTEM}, {
            "role": "user",
            "content": (
                "Create an article brief for Internet in Myanmar from these sources.\n\n"
                f"{combined}\n\n"
                + BRIEF_JSON_SPEC
            ),
        }],
    )
    brief = _parse_json(response.choices[0].message.content)
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

    response = CLIENT.chat.completions.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        messages=[{"role": "system", "content": BRIEF_SYSTEM}, {
            "role": "user",
            "content": (
                "Create an article brief for Internet in Myanmar on this topic.\n\n"
                + prompt_content
                + BRIEF_JSON_SPEC
                + "\nIf sources are insufficient, set confidence below 0.5 and note in angle."
            ),
        }],
    )
    brief = _parse_json(response.choices[0].message.content)
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
    response = CLIENT.chat.completions.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        messages=[{"role": "system", "content": BRIEF_SYSTEM}, {
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
    brief = _parse_json(response.choices[0].message.content)
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

    response = CLIENT.chat.completions.create(
        model=_get_model("brief"),
        max_tokens=_get_max_tokens("brief"),
        messages=[{"role": "system", "content": BRIEF_SYSTEM}, {
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
    brief = _parse_json(response.choices[0].message.content)
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

    # Build coverage index once for the whole run
    coverage_index = _build_coverage_index(days=30)
    log.info(f"Coverage index: {len(coverage_index)} recent briefs/articles loaded")

    # Cluster related items so multi-source stories become one brief
    clusters = _cluster_items(eligible)

    for cluster in clusters:
        # Use highest-scored item's title for overlap check
        rep = max(cluster, key=lambda x: x.get("score", 0))
        title = rep.get("title", "")
        summary = rep.get("summary", rep.get("description", ""))

        overlap = _check_overlap(title, summary, coverage_index)
        verdict = overlap.get("verdict", "UNIQUE")

        if verdict == "DUPLICATE":
            log.info(
                f"SKIP (duplicate) — {title!r} | "
                f"Reason: {overlap.get('reason')} | "
                f"Related: {overlap.get('related')}"
            )
            continue

        prior = overlap.get("related") if verdict == "NEW_DEVELOPMENT" else None
        if verdict == "NEW_DEVELOPMENT":
            log.info(f"NEW DEVELOPMENT — {title!r} | Related: {prior}")

        src_count = len(cluster)
        log.info(f"Generating brief from {src_count} source(s): {title[:60]}")
        try:
            brief = generate_brief_from_cluster(cluster, prior_coverage=prior)
            brief["id"] = str(uuid.uuid4())
            if src_count > 1:
                brief["source_count"] = src_count
            _save_brief(brief)
        except Exception as e:
            log.error(f"Failed for cluster '{title[:50]}': {e}")


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
