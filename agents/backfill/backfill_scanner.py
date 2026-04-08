"""
agents/backfill/backfill_scanner.py

Searches 3 years of content from priority sources.
Scores relevance with Claude Haiku via model_router.
Outputs a CSV for manual approval before anything is published.

Usage:
  python agents/backfill/backfill_scanner.py
  python agents/backfill/backfill_scanner.py --dry-run   # 2 topics, 3 results each
"""

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from datetime import datetime, date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent.parent
AGENTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AGENTS_DIR))

from utils.model_router import _get_tavily, _call_deepseek

# ── Config ────────────────────────────────────────────────────────────────────
DATE_FROM = "2021-02-01"   # coup period start
DATE_TO   = "2024-04-01"   # 3 years back

OUTPUT_DIR     = Path(__file__).parent
SOURCE_DB_PATH = AGENTS_DIR / "data" / "source_scores.json"

with open(SOURCE_DB_PATH) as f:
    SOURCE_SCORES = json.load(f)

PRIORITY_DOMAINS = [
    "ooni.org", "netblocks.org", "accessnow.org",
    "citizenlab.ca", "freedomhouse.org", "rsf.org",
    "hrw.org", "irrawaddy.com", "dvb.no", "myanmar-now.org",
    "mizzima.com", "cpj.org", "amnesty.org", "reuters.com",
    "apnews.com", "theguardian.com", "bbc.com",
    "khitthitmedia.com", "athanfreeexpression.org",
]

SEARCH_TOPICS = [
    "Myanmar internet shutdown",
    "Myanmar internet censorship",
    "Myanmar VPN blocked",
    "Myanmar social media blocked",
    "Myanmar internet freedom",
    "Myanmar digital rights",
    "Myanmar journalist arrested digital",
    "Myanmar press freedom online",
    "Myanmar OONI measurement",
    "Myanmar BGP shutdown network",
    "Myanmar Facebook blocked",
    "Myanmar Signal Telegram blocked",
    "Myanmar firewall surveillance",
    "Myanmar network disruption",
    "Myanmar cyber law regulation",
    "Myanmar internet junta",
    "Myanmar Great Firewall China",
    "Myanmar Mytel MPT Ooredoo block",
    "Myanmar broadband mobile shutdown",
    "Myanmar NetBlocks disruption",
    "Myanmar Citizen Lab report",
    "Myanmar Freedom House internet",
    "Myanmar Access Now KeepItOn",
    "Myanmar digital surveillance technology",
    "Myanmar online censorship coup",
]

INTERNAL_RUBRIC_PROMPT = """Score this news source on 5 criteria. Total: 100 points.
Source domain: {domain}
Source name: {name}
Context: This site covers Myanmar digital rights and internet freedom.

CRITERION 1 — Editorial independence (30 points)
  30: Editorially independent, no government or corporate control
  20: Mostly independent, some ownership concerns
  10: Partial government or institutional affiliation
   0: State-controlled or known propaganda outlet

CRITERION 2 — Track record on Myanmar coverage (25 points)
  25: Established, long track record, cited by major institutions
  20: Good track record, occasional factual issues corrected
  10: Mixed track record, some uncorrected errors
   0: Known to publish false information or propaganda

CRITERION 3 — Transparency (20 points)
  20: Clear ownership, funding, editorial standards published
  15: Mostly transparent, minor gaps
  10: Partial transparency
   0: Anonymous, unknown ownership

CRITERION 4 — Source practices (15 points)
  15: Primary sources, named sources, data cited
  10: Mix of primary and secondary sourcing
   5: Mostly secondary, limited original reporting
   0: No sourcing, anonymous claims only

CRITERION 5 — Correction culture (10 points)
  10: Issues corrections promptly and transparently
   5: Corrects errors but without prominence
   0: Never issues corrections

Return JSON only:
{{
  "domain": "{domain}",
  "editorial_independence": 0,
  "track_record": 0,
  "transparency": 0,
  "source_practices": 0,
  "correction_culture": 0,
  "total": 0,
  "tier": "A",
  "label": "Highly Reliable",
  "notes": "one-line explanation"
}}"""

RELEVANCE_PROMPT = """Rate this article's relevance to Myanmar internet freedom,
digital censorship, network shutdowns, VPN blocking, journalist
digital safety, press freedom online, or surveillance technology.

Title: {title}
Excerpt: {excerpt}
Source: {source}
Date: {date}

JSON only:
{{
  "relevance_score": 0,
  "category": "Shutdown",
  "tags": ["tag1", "tag2"],
  "reason": "one sentence",
  "your_title": "reworded title for our site (different from original, same meaning)"
}}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def load_seen_urls(seen_file: Path) -> set:
    if not seen_file.exists():
        return set()
    return set(seen_file.read_text().splitlines())


def mark_seen(url: str, seen_file: Path):
    with open(seen_file, "a") as f:
        f.write(url_hash(url) + "\n")


def get_source_score(url: str) -> dict:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "")

    if domain in SOURCE_SCORES:
        return SOURCE_SCORES[domain]

    # Unknown source — score with DeepSeek
    raw = _call_deepseek(
        INTERNAL_RUBRIC_PROMPT.format(domain=domain, name=domain),
        "",
        250,
    )
    try:
        # Strip markdown fences if present
        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        result = json.loads(raw)
        result.setdefault("name", domain)
        result.setdefault("type", "unknown")
        result.setdefault("scored_by", "internal-auto")
        result.setdefault("scored_at", date.today().isoformat())
        SOURCE_SCORES[domain] = result
        with open(SOURCE_DB_PATH, "w") as f:
            json.dump(SOURCE_SCORES, f, indent=2)
        return result
    except json.JSONDecodeError:
        return {"name": domain, "total": 50, "tier": "C", "label": "Use with Caution", "notes": "auto-score failed"}


def score_article(item: dict) -> dict | None:
    prompt = RELEVANCE_PROMPT.format(
        title=item.get("title", ""),
        excerpt=item.get("content", "")[:400],
        source=item.get("url", ""),
        date=item.get("published_date", ""),
    )
    raw = _call_deepseek(prompt, "", 250)
    try:
        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def in_date_range(published_date_str: str) -> bool:
    """Filter Tavily results to DATE_FROM–DATE_TO range."""
    if not published_date_str:
        return True  # no date info → keep
    try:
        d = datetime.fromisoformat(published_date_str[:10]).date()
        return date.fromisoformat(DATE_FROM) <= d <= date.fromisoformat(DATE_TO)
    except (ValueError, TypeError):
        return True


# ── Main scanner ──────────────────────────────────────────────────────────────

def run(dry_run: bool = False):
    today       = date.today().isoformat()
    output_file = OUTPUT_DIR / f"candidates_{today}.csv"
    seen_file   = OUTPUT_DIR / "seen_urls.txt"
    seen_urls   = load_seen_urls(seen_file)

    tavily    = _get_tavily()
    topics    = SEARCH_TOPICS[:2] if dry_run else SEARCH_TOPICS
    max_res   = 3 if dry_run else 20
    candidates = []

    for topic in topics:
        print(f"\nSearching: {topic}")

        try:
            results = tavily.search(
                query=topic,
                search_depth="advanced",
                include_domains=PRIORITY_DOMAINS,
                max_results=max_res,
            )
            items = results.get("results", [])
        except Exception as e:
            print(f"  ! Tavily error: {e}")
            continue

        for item in items:
            url = item.get("url", "")
            if not url:
                continue

            uid = url_hash(url)
            if uid in seen_urls:
                continue

            # Date filter
            pub_date = item.get("published_date", "")
            if not in_date_range(pub_date):
                continue

            mark_seen(url, seen_file)
            seen_urls.add(uid)

            # Relevance scoring
            relevance = score_article(item)
            if relevance is None:
                print(f"  ! Score parse failed: {item.get('title', '')[:50]}")
                continue

            score = min(10, relevance.get("relevance_score", 0))
            if score < 6:
                print(f"  ✗ [{score}/10] {item.get('title', '')[:60]}")
                continue

            # Source credibility
            source_info = get_source_score(url)

            candidate = {
                "date":             pub_date[:10] if pub_date else "",
                "title_original":   item.get("title", ""),
                "title_yours":      relevance.get("your_title", item.get("title", "")),
                "url":              url,
                "source":           source_info.get("name", ""),
                "excerpt":          item.get("content", "")[:300],
                "relevance_score":  score,
                "category":         relevance.get("category", "Other"),
                "tags":             "|".join(relevance.get("tags", [])),
                "relevance_reason": relevance.get("reason", ""),
                "source_score":     source_info.get("total", 0),
                "source_tier":      source_info.get("tier", "C"),
                "source_label":     source_info.get("label", ""),
                "source_notes":     source_info.get("notes", ""),
                "decision":         "",   # PUBLISH / SKIP / LATER
                "your_notes":       "",
            }

            candidates.append(candidate)
            print(f"  ✓ [{score}/10] [{source_info.get('tier','?')}] {item.get('title','')[:60]}")

    # Sort: most recent first, then by relevance
    candidates.sort(key=lambda x: (x["date"], x["relevance_score"]), reverse=True)

    if candidates:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(candidates[0].keys()))
            writer.writeheader()
            writer.writerows(candidates)

        print(f"\n✅ {len(candidates)} candidates → {output_file}")
        print("Open in Google Sheets. Fill 'decision' column: PUBLISH / SKIP / LATER")
        print("Then run: python agents/backfill/backfill_publisher.py " + str(output_file))
    else:
        print("\nNo candidates found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="2 topics, 3 results — quick test")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
