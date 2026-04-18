"""
WP Migrator
-----------
Reads migration_review.csv (Decision=OK rows), fetches full article content
from WordPress DB, converts HTML→MDX, writes to src/content/articles/.
Also generates public/_redirects for Cloudflare Pages.

No LLM required — pure rule-based conversion.

Usage:
  python wp_migrator.py                    # migrate all OK articles
  python wp_migrator.py --dry-run          # show what would happen, write nothing
  python wp_migrator.py --limit 5          # migrate first 5 only (test)
  python wp_migrator.py --slug some-slug   # migrate single article by WP slug
"""

import csv
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
from bs4 import BeautifulSoup, Comment

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent.parent
ARTICLES_DIR = REPO_ROOT / "src" / "content" / "articles"
REDIRECTS    = REPO_ROOT / "public" / "_redirects"
CSV_PATH     = Path("/mnt/c/Dev/iimv2/migration_review.csv")

import os as _os
from dotenv import load_dotenv as _load
_load()
DB = dict(
    host="127.0.0.1", port=3307,
    database=_os.getenv("WP_DB_NAME", "internetinmyanmar"),
    user=_os.getenv("WP_DB_USER", "claudagent"),
    password=_os.getenv("WP_DB_PASSWORD_READONLY", ""),
)

# ── Category mapping WP→IIM ───────────────────────────────────────────────────

CATEGORY_MAP = {
    "Analysis":   "Censorship & Shutdowns",
    "Toolbox":    "Guides & Tools",
    "Broadband":  "News - Broadband",
    "Mobile":     "News - Mobile",
    "News":       "News - Policy",
    "Business":   "Digital Economy",
    "OTT":        "Digital Economy",
    "Stories":    "Censorship & Shutdowns",
    "English":    "Censorship & Shutdowns",
}

DEFAULT_CATEGORY = "News - Policy"

# ── Slug helpers ──────────────────────────────────────────────────────────────

def clean_slug(wp_slug: str) -> str:
    """Sanitize WP slug: lowercase, hyphens, no trailing slash."""
    s = wp_slug.lower().strip("/")
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80]

# ── HTML → MDX conversion ─────────────────────────────────────────────────────

def html_to_mdx(raw_html: str, wp_slug: str) -> str:
    """
    Convert WordPress HTML content to clean MDX.
    - Strip Gutenberg block comments
    - Remove inline styles
    - Rewrite image paths
    - Clean up anchor tags
    - Remove empty elements
    """
    # Strip Gutenberg block comments
    content = re.sub(r"<!-- /?wp:[^>]* -->", "", raw_html)

    soup = BeautifulSoup(content, "lxml")

    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove inline styles from all elements
    for tag in soup.find_all(True):
        tag.attrs.pop("style", None)
        tag.attrs.pop("class", None)
        tag.attrs.pop("id", None)

    # Rewrite image src: WP uploads → local path placeholder
    for img in soup.find_all("img"):
        src = img.get("src", "")
        filename = src.split("/")[-1].split("?")[0]
        # Strip dimensions suffix: image-800x600.jpg → image.jpg
        filename = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", filename)
        img["src"] = f"/images/{wp_slug}/{filename}"

        # Rewrite alt text: strip keyword stuffing (keep if reasonable)
        alt = img.get("alt", "")
        if len(alt.split()) > 12:
            img["alt"] = " ".join(alt.split()[:10])
        if not img.get("alt"):
            img["alt"] = "Myanmar internet censorship"
        img["loading"] = "lazy"

    # Remove empty paragraphs
    for p in soup.find_all("p"):
        if not p.get_text(strip=True):
            p.decompose()

    # Remove WordPress shortcodes that survived
    text = str(soup)
    text = re.sub(r"\[/?[a-z_]+[^\]]*\]", "", text)

    # Re-parse cleaned HTML and convert to simple MDX
    soup2 = BeautifulSoup(text, "lxml")
    body = soup2.find("body")
    if not body:
        body = soup2

    return _node_to_mdx(body).strip()


def _node_to_mdx(node) -> str:
    """Recursively convert a BeautifulSoup node to MDX string."""
    from bs4 import NavigableString, Tag

    if isinstance(node, NavigableString):
        return str(node)

    tag = node.name
    children = "".join(_node_to_mdx(c) for c in node.children)

    if tag in ("html", "body", "div", "section", "article", "span"):
        return children
    if tag == "p":
        text = children.strip()
        return f"\n\n{text}\n\n" if text else ""
    if tag == "br":
        return "\n"
    if tag == "h1":
        return f"\n\n## {children.strip()}\n\n"
    if tag == "h2":
        return f"\n\n## {children.strip()}\n\n"
    if tag == "h3":
        return f"\n\n### {children.strip()}\n\n"
    if tag == "h4":
        return f"\n\n#### {children.strip()}\n\n"
    if tag in ("strong", "b"):
        return f"**{children}**"
    if tag in ("em", "i"):
        return f"_{children}_"
    if tag == "a":
        href = node.get("href", "")
        text = children.strip()
        if not text:
            return href
        # Convert WP internal links to relative
        href = re.sub(r"https?://(?:www\.)?internetinmyanmar\.com", "", href)
        return f"[{text}]({href})"
    if tag == "img":
        src = node.get("src", "")
        alt = node.get("alt", "")
        return f"\n\n![{alt}]({src})\n\n"
    if tag in ("ul", "ol"):
        items = []
        for li in node.find_all("li", recursive=False):
            text = _node_to_mdx(li).strip()
            items.append(f"- {text}")
        return "\n\n" + "\n".join(items) + "\n\n"
    if tag == "li":
        return children.strip()
    if tag == "blockquote":
        lines = children.strip().splitlines()
        quoted = "\n".join(f"> {l}" for l in lines)
        return f"\n\n{quoted}\n\n"
    if tag in ("pre", "code"):
        return f"`{children}`"
    if tag == "hr":
        return "\n\n---\n\n"
    if tag == "figure":
        return children
    if tag == "figcaption":
        return f"\n_{children.strip()}_\n"
    if tag in ("table", "thead", "tbody", "tr", "td", "th"):
        return children  # Keep table content as text for now

    # Unknown tag — return children
    return children


# ── Frontmatter builder ───────────────────────────────────────────────────────

def _map_category(wp_categories: str) -> str:
    for cat in wp_categories.split(", "):
        if cat.strip() in CATEGORY_MAP:
            return CATEGORY_MAP[cat.strip()]
    return DEFAULT_CATEGORY


def _is_stale(pub_date: datetime) -> bool:
    return (datetime.now(timezone.utc) - pub_date.replace(tzinfo=timezone.utc)).days > 548


def _word_count_to_reading_time(word_count: int) -> int:
    return max(1, round(word_count / 200))


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax to produce plain text."""
    # Remove links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    # Remove bold/italic
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Remove blockquote markers
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _excerpt_from_content(content: str, max_chars: int = 280) -> str:
    """Extract first meaningful paragraph as plain text excerpt."""
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    for line in lines:
        if len(line) > 60 and not line.startswith("#") and not line.startswith("!"):
            clean = _strip_markdown(line)
            return clean[:max_chars].rstrip(".,;:") + ("…" if len(clean) > max_chars else "")
    return _strip_markdown(lines[0])[:max_chars] if lines else ""


def build_frontmatter(row: dict, post: dict, slug: str) -> str:
    """Build YAML frontmatter for an MDX article."""
    pub_date = post["post_date"]
    if isinstance(pub_date, str):
        pub_date = datetime.fromisoformat(pub_date)

    category = _map_category(post.get("categories", ""))
    word_count = post.get("word_count", 500)
    reading_time = _word_count_to_reading_time(word_count)

    title = post["title"].replace('"', "'")

    # SEO title: prefer Yoast title, fall back to post title (max 60 chars)
    yoast_title = (post.get("yoast_title") or "").strip()
    # Yoast titles often have %%sep%% %%sitename%% tokens — strip them
    yoast_title = re.sub(r'\s*%%[^%]+%%\s*', '', yoast_title).strip()
    seo_title = yoast_title[:60] if yoast_title else (title[:57] + "…" if len(title) > 60 else title)

    # Yoast meta description (already written, plain text)
    yoast_meta = (post.get("yoast_meta") or "").strip().replace('"', "'")
    yoast_meta = yoast_meta[:152] + "…" if len(yoast_meta) > 155 else yoast_meta

    # Tags from WP (deduplicated)
    raw_tags = post.get("tags") or ""
    tags = list(dict.fromkeys(
        t.strip() for t in raw_tags.split("|||") if t.strip()
    ))[:5]  # max 5 tags
    tags_json = json.dumps(tags)

    original_url = f"https://www.internetinmyanmar.com/{post['wp_slug']}/"

    fm = f"""---
title: "{title}"
seoTitle: "{seo_title}"
metaDescription: "{yoast_meta}"
category: "{category}"
tags: {tags_json}
author: "Anna"
publishedAt: {pub_date.strftime('%Y-%m-%d')}
draft: false
excerpt: ""
readingTime: {reading_time}
lang: "en"
migrated: true
originalUrl: "{original_url}"
---"""
    return fm


# ── DB query ──────────────────────────────────────────────────────────────────

def fetch_posts(slugs: list[str] | None = None) -> dict[str, dict]:
    """Fetch full post content from WP DB including Yoast SEO and tags."""
    conn = mysql.connector.connect(**DB)
    cur = conn.cursor(dictionary=True)

    where = "p.post_status = 'publish' AND p.post_type = 'post'"
    if slugs:
        placeholders = ", ".join(["%s"] * len(slugs))
        where += f" AND p.post_name IN ({placeholders})"

    cur.execute(f"""
        SELECT p.ID, p.post_title as title, p.post_date, p.post_name as wp_slug,
               p.post_content as content,
               ROUND(LENGTH(p.post_content) / 5) as word_count,
               u.display_name as author,
               GROUP_CONCAT(DISTINCT CASE WHEN tt.taxonomy='category' THEN t.name END ORDER BY t.name SEPARATOR ', ') as categories,
               GROUP_CONCAT(DISTINCT CASE WHEN tt.taxonomy='post_tag' THEN t.name END ORDER BY t.name SEPARATOR '|||') as tags,
               MAX(CASE WHEN pm.meta_key='_yoast_wpseo_metadesc' THEN pm.meta_value END) as yoast_meta,
               MAX(CASE WHEN pm.meta_key='_yoast_wpseo_title' THEN pm.meta_value END) as yoast_title,
               MAX(CASE WHEN pm.meta_key='_yoast_wpseo_focuskw' THEN pm.meta_value END) as focus_kw
        FROM wp_posts p
        LEFT JOIN wp_users u ON u.ID = p.post_author
        LEFT JOIN wp_term_relationships tr ON p.ID = tr.object_id
        LEFT JOIN wp_term_taxonomy tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
            AND tt.taxonomy IN ('category', 'post_tag')
        LEFT JOIN wp_terms t ON tt.term_id = t.term_id
        LEFT JOIN wp_postmeta pm ON p.ID = pm.post_id
            AND pm.meta_key IN ('_yoast_wpseo_metadesc','_yoast_wpseo_title','_yoast_wpseo_focuskw')
        WHERE {where}
        GROUP BY p.ID
    """, slugs if slugs else None)

    posts = {row["wp_slug"]: row for row in cur.fetchall()}
    conn.close()
    return posts


# ── Redirects ─────────────────────────────────────────────────────────────────

def append_redirect(wp_slug: str, new_slug: str, migrate: bool) -> None:
    REDIRECTS.parent.mkdir(parents=True, exist_ok=True)
    existing = REDIRECTS.read_text() if REDIRECTS.exists() else ""
    target = f"/articles/{new_slug}" if migrate else "/"
    line = f"/{wp_slug}/ {target} 301\n"
    if line not in existing:
        with open(REDIRECTS, "a") as f:
            f.write(line)


# ── Main migration ────────────────────────────────────────────────────────────

def migrate(dry_run: bool = False, limit: int | None = None, only_slug: str | None = None):
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    # Read CSV
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    ok_rows = [r for r in rows if r.get("Decision", "").strip().upper() == "OK"]
    nok_rows = [r for r in rows if r.get("Decision", "").strip().upper() == "NOK"]

    print(f"CSV: {len(ok_rows)} OK, {len(nok_rows)} NOK", file=sys.stderr)

    if only_slug:
        # Find the WP slug from CSV title match — or just use it directly
        ok_rows = [r for r in ok_rows if only_slug in r.get("Title", "").lower()]
        print(f"Filtered to {len(ok_rows)} rows matching '{only_slug}'", file=sys.stderr)

    if limit:
        ok_rows = ok_rows[:limit]

    # Fetch WP content for OK rows
    # We need to match CSV rows to WP slugs. The CSV has Title but not slug.
    # Fetch all posts and match by title.
    print("Fetching WP content…", file=sys.stderr)
    all_posts = fetch_posts()
    print(f"Fetched {len(all_posts)} posts from DB", file=sys.stderr)

    # Build title→post lookup (case-insensitive)
    title_lookup = {p["title"].lower(): p for p in all_posts.values()}

    migrated_count = 0
    skipped_count = 0
    redirects = []

    for row in ok_rows:
        csv_title = row.get("Title", "").strip()
        post = title_lookup.get(csv_title.lower())

        if not post:
            # Try partial match
            for t, p in title_lookup.items():
                if csv_title.lower()[:40] in t:
                    post = p
                    break

        if not post:
            print(f"  ⚠  No DB match: {csv_title[:60]}", file=sys.stderr)
            skipped_count += 1
            continue

        wp_slug = post["wp_slug"]
        new_slug = clean_slug(wp_slug)
        out_path = ARTICLES_DIR / f"{new_slug}.mdx"

        if out_path.exists():
            print(f"  → Exists, skipping: {new_slug}", file=sys.stderr)
            redirects.append((wp_slug, new_slug, True))
            continue

        # Convert content
        raw_html = post.get("content", "") or ""
        mdx_content = html_to_mdx(raw_html, new_slug)

        # Excerpt: prefer Yoast meta (already plain text), fall back to first paragraph
        yoast_meta_val = (post.get("yoast_meta") or "").strip().replace('"', "'")
        if yoast_meta_val:
            excerpt = yoast_meta_val[:280]
        else:
            excerpt = _excerpt_from_content(mdx_content)
            excerpt = excerpt.replace('"', "'").replace('\n', ' ')[:280]

        # Build frontmatter (already has metaDescription from Yoast)
        fm = build_frontmatter(row, post, new_slug)
        # Only inject excerpt into frontmatter
        fm = fm.replace('excerpt: ""', f'excerpt: "{excerpt[:280]}"')

        # Stale notice
        pub_date = post["post_date"]
        if isinstance(pub_date, str):
            pub_date = datetime.fromisoformat(pub_date)
        stale_notice = ""
        if _is_stale(pub_date):
            year = pub_date.year
            stale_notice = f"\n> ⚠️ First published in {year}. Some figures may be outdated.\n\n"

        full_mdx = f"{fm}\n\n{stale_notice}{mdx_content}\n"

        if dry_run:
            print(f"  [DRY] Would write: {out_path.name} ({len(full_mdx)} chars)", file=sys.stderr)
        else:
            out_path.write_text(full_mdx, encoding="utf-8")
            print(f"  ✓ {out_path.name}", file=sys.stderr)

        redirects.append((wp_slug, new_slug, True))
        migrated_count += 1

    # Write redirects for NOK rows (→ homepage)
    for row in nok_rows:
        csv_title = row.get("Title", "").strip()
        post = title_lookup.get(csv_title.lower())
        if post:
            redirects.append((post["wp_slug"], "", False))

    # Write _redirects file
    if not dry_run:
        REDIRECTS.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        seen = set()
        for wp_slug, new_slug, migrate in redirects:
            target = f"/articles/{new_slug}" if migrate else "/"
            line = f"/{wp_slug}/ {target} 301"
            if line not in seen:
                lines.append(line)
                seen.add(line)
        REDIRECTS.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
        print(f"\n✓ _redirects written: {len(lines)} rules", file=sys.stderr)

    print(f"\nDone: {migrated_count} migrated, {skipped_count} skipped (no DB match)", file=sys.stderr)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    only_slug = None
    limit = None

    if "--slug" in sys.argv:
        idx = sys.argv.index("--slug")
        only_slug = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None

    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 5

    migrate(dry_run=dry_run, limit=limit, only_slug=only_slug)
