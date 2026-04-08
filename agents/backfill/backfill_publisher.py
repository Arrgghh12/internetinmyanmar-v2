"""
agents/backfill/backfill_publisher.py

Reads approved rows from a candidates CSV and creates MDX digest files.
Run after filling the 'decision' column in the spreadsheet.

Usage:
  python agents/backfill/backfill_publisher.py candidates_YYYY-MM-DD.csv
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT        = Path(__file__).parent.parent.parent
CONTENT_DIR = ROOT / "src" / "content" / "digest"
CONTENT_DIR.mkdir(parents=True, exist_ok=True)


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
                print(f"  ⚠️  No date for: {row.get('title_original', '')[:50]} — skipping")
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
