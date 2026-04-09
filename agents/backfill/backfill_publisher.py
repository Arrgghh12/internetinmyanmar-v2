"""
agents/backfill/backfill_publisher.py

Reads approved rows from a candidates CSV and creates MDX digest files.
Run after filling the 'decision' column in the spreadsheet.

Usage:
  python agents/backfill/backfill_publisher.py candidates_YYYY-MM-DD.csv
"""

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT        = Path(__file__).parent.parent.parent
CONTENT_DIR = ROOT / "src" / "content" / "digest"
CONTENT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; IIMBot/1.0; +https://internetinmyanmar.com)",
    "Accept": "text/html,application/xhtml+xml",
}


def fetch_article_date(url: str) -> str | None:
    """
    Fetch article URL and extract the original publication date.
    Tries in order:
      1. JSON-LD datePublished
      2. <meta property="article:published_time">
      3. <meta name="date"> / <meta name="pubdate">
      4. <time datetime="..."> (first one found)
    Returns ISO date string "YYYY-MM-DD" or None if not found.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code >= 400:
            return _date_from_url(url)
        soup = BeautifulSoup(r.text, "lxml")

        # 1. JSON-LD datePublished
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                items = data if isinstance(data, list) else [data]
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for key in ("datePublished", "dateCreated", "uploadDate"):
                        d = _normalize_date(item.get(key, ""))
                        if d:
                            return d
            except Exception:
                pass

        # 2. Meta tags
        for attr, name in [
            ("property", "article:published_time"),
            ("property", "og:article:published_time"),
            ("name",     "date"),
            ("name",     "pubdate"),
            ("name",     "publish-date"),
            ("name",     "publication_date"),
            ("name",     "DC.date"),
            ("name",     "DC.Date"),
            ("name",     "sailthru.date"),
            ("name",     "parsely-pub-date"),
            ("name",     "cxenseparse:recs:publishtime"),
            ("itemprop", "datePublished"),
            ("itemprop", "dateCreated"),
        ]:
            tag = soup.find("meta", attrs={attr: name})
            if tag and tag.get("content"):
                d = _normalize_date(tag["content"])
                if d:
                    return d

        # 3. <time datetime="...">
        for time_tag in soup.find_all("time", attrs={"datetime": True}):
            d = _normalize_date(time_tag["datetime"])
            if d:
                return d

    except Exception:
        pass

    # 4. Fallback: extract date from URL path (e.g. /2021/02/01/)
    return _date_from_url(url)


def _normalize_date(raw: str) -> str | None:
    """Parse any date string into YYYY-MM-DD."""
    if not raw:
        return None
    raw = raw.strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
                "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[:20], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _date_from_url(url: str) -> str | None:
    """Extract date from URL patterns like /2021/02/01/ or /2021-02-01."""
    # Standard /YYYY/MM/DD/ or -YYYY-MM-DD
    m = re.search(r"/(\d{4})[/_-](\d{2})[/_-](\d{2})", url)
    if m:
        y, mo, d = m.groups()
        if 2000 <= int(y) <= 2030 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{mo}-{d}"
    # Year-only in slug: e.g. /reports/2022/ or ?year=2022 — not precise enough, skip
    return None


def _date_from_text(text: str) -> str | None:
    """
    Extract a publication date from free text (excerpt, title).
    Looks for explicit date phrases, not just any date-like string.
    Returns YYYY-MM-DD or None.
    """
    if not text:
        return None
    # "January 15, 2021" / "Jan 15, 2021"
    m = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December"
        r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[\s.]+(\d{1,2})[,\s]+(\d{4})\b",
        text, re.IGNORECASE,
    )
    if m:
        d = _normalize_date(f"{m.group(1)} {m.group(2)}, {m.group(3)}")
        if d:
            return d
    # "15 January 2021"
    m = re.search(
        r"\b(\d{1,2})[\s.]+(January|February|March|April|May|June|July|August|September|October"
        r"|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s.,]+(\d{4})\b",
        text, re.IGNORECASE,
    )
    if m:
        d = _normalize_date(f"{m.group(2)} {m.group(1)}, {m.group(3)}")
        if d:
            return d
    # ISO date at start of excerpt (Tavily sometimes prepends it)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text.strip())
    if m:
        return _normalize_date(m.group(1))
    return None


def _date_from_wayback(url: str) -> str | None:
    """
    Query the Wayback Machine availability API for the closest archived snapshot.
    The first snapshot timestamp is usually within days of the original publish date.
    """
    try:
        api = f"https://archive.org/wayback/available?url={url}"
        r = requests.get(api, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        snap = r.json().get("archived_snapshots", {}).get("closest", {})
        if snap.get("available") and snap.get("timestamp"):
            ts = snap["timestamp"]  # format: YYYYMMDDHHmmss
            y, mo, d = ts[:4], ts[4:6], ts[6:8]
            if 2000 <= int(y) <= 2030 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                return f"{y}-{mo}-{d}"
    except Exception:
        pass
    return None


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:60].strip("-")


def make_mdx(row: dict) -> str:
    tags      = [t.strip() for t in row["tags"].split("|") if t.strip()]
    tags_yaml = "\n".join([f'  - "{t}"' for t in tags])
    excerpt   = row["excerpt"].strip()

    # Ensure excerpt ends cleanly
    if excerpt and not excerpt.endswith((".", "...", "?", "!")):
        excerpt = excerpt.rsplit(" ", 1)[0] + "..."

    title_safe  = row["title_yours"].replace('"', "'")
    source_safe = row["title_original"].replace('"', "'")
    added_at    = datetime.now().date().isoformat()

    return f"""---
title: "{title_safe}"
sourceTitle: "{source_safe}"
source: "{row['source']}"
sourceUrl: "{row['url']}"
canonical: "{row['url']}"
publishedAt: {row['date']}
addedAt: {added_at}
category: "{row['category']}"
tags:
{tags_yaml}
sourceScore: {row['source_score']}
sourceTier: "{row['source_tier']}"
sourceLabel: "{row['source_label']}"
type: "digest"
draft: false
---

*Originally published by [{row['source']}]({row['url']}) on {row['date']}.*

> {excerpt}

[Read the full article on {row['source']} →]({row['url']})
"""


def run(csv_file: str):
    created = 0
    skipped = 0

    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            decision = row.get("decision", "").strip().upper()

            if decision != "PUBLISH":
                skipped += 1
                continue

            if not row.get("date"):
                url     = row.get("url", "")
                excerpt = row.get("excerpt", "")
                title   = row.get("title_original", "")

                # 1. Try excerpt / title text (free, no HTTP)
                fetched = _date_from_text(excerpt) or _date_from_text(title)
                if fetched:
                    row["date"] = fetched
                    print(f"  🔍 Date from text: {fetched} — {title[:50]}")
                else:
                    # 2. Try fetching the article page
                    print(f"  🔍 No date for: {title[:50]} — fetching from URL…")
                    fetched = fetch_article_date(url)
                    if fetched:
                        row["date"] = fetched
                        print(f"     → found via page: {fetched}")
                    else:
                        # 3. Wayback Machine CDX fallback
                        print(f"     → trying Wayback Machine…")
                        fetched = _date_from_wayback(url)
                        if fetched:
                            row["date"] = fetched
                            print(f"     → found via Wayback: {fetched}")
                        else:
                            print(f"  ⚠️  Could not determine date — skipping")
                            skipped += 1
                            continue

            if not row.get("excerpt", "").strip():
                print(f"  ⚠️  No excerpt for: {row.get('title_original', '')[:50]} — skipping")
                skipped += 1
                continue

            slug     = slugify(row["title_yours"])
            filename = f"{row['date']}-{slug}.mdx"
            out_path = CONTENT_DIR / filename

            if out_path.exists():
                print(f"  ⚠️  Duplicate skipped: {filename}")
                skipped += 1
                continue

            out_path.write_text(make_mdx(row), encoding="utf-8")
            created += 1
            print(f"  ✓ {filename}")

    print(f"\n✅ {created} digest pages created, {skipped} skipped.")
    if created:
        print("Commit and push to trigger Cloudflare Pages rebuild:")
        print("  git add src/content/digest/ && git commit -m 'backfill: digest pages'")
        print("  git push origin main")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backfill_publisher.py candidates_YYYY-MM-DD.csv")
        sys.exit(1)
    run(sys.argv[1])
