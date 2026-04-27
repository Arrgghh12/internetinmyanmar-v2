# /iim-article — Impactful Article Skill v2.0

Two-phase article production: draft article first → Anna approves online →
then social campaign + newsletter. Nothing merges, nothing sends without approval.

## Usage

```
/iim-article <brief-path-or-topic>
/iim-article agents/approved/2026-04-26/myanmar-vpn-blocks.md
/iim-article "ISP throttling of Signal in Yangon, April 2026"
```

---

## Design Principles

- Data-First: open with the single most surprising finding
- 7-section MDX template (see Phase 1)
- 2–3 interactive `<CensorshipChart>` embeds
- Author: Anna — always, no exceptions
- Nothing publishes without Anna's explicit approval

---

## PHASE 1 — Draft Article + Online Preview

### Step 0 — Validation Checklist (stop and wait for OK)

Before writing anything, present this checklist:

```
ARTICLE DRAFT PLAN — [Title]
══════════════════════════════════════
Slug:        [lowercase-hyphens-max-6-words]
SEO title:   [max 60 chars]
Meta:        [max 155 chars]
Category:    [one of the 7 approved categories]
Lead:        [1-sentence summary of the opening finding]
Charts:      [2–3 CensorshipChart types, e.g. ooni-monthly, bgp-ooni-combined]
Word count:  ~[estimate]
══════════════════════════════════════
Reply OK to write the article, or describe changes.
```

Wait for OK before continuing.

### Step 1 — Write the MDX Article

Output the full MDX file for `src/content/articles/[slug].mdx`.

**Frontmatter** (all fields required, `draft: true` always):
```yaml
---
title: "[full title]"
seoTitle: "[max 60 chars — primary keyword first]"
metaDescription: "[max 155 chars — factual, no stuffing]"
slug: "[lowercase-hyphens-max-6-words]"
category: "[Censorship & Shutdowns | Telecom & Infrastructure | Digital Economy | Guides & Tools | News - Mobile | News - Broadband | News - Policy]"
tags: ["tag1", "tag2", "tag3"]
author: "Anna"
publishedAt: [YYYY-MM-DD today]
draft: true
excerpt: "[max 300 chars]"
lang: "en"
sources:
  - "https://..."
---
```

**7-Section Body**:
1. **Hero** — bold subtitle or pull-quote to open the body
2. **Lead Insight** — 1–2 paragraphs, single most surprising finding with a specific statistic
3. **Context & Background** — history + why this matters now, 1–2 paragraphs
4. **Data Analysis** — 2–3 `<CensorshipChart>` embeds with analysis:
   ```mdx
   <CensorshipChart type="ooni-monthly" title="OONI Anomaly Rate, 2021–2026" />
   ```
   Supported types: `live-signal | ooni-monthly | election-window | ooni-breakdown | blocked-sites | category-blocks | bgp-ooni-combined`
5. **Key Findings & Implications** — 4–6 numbered findings, specific and actionable
6. **Methodology & Limitations** — OONI probe density, CF Radar proxy limitations, Access Now coverage
7. **Sources & Dataset**:
   ```mdx
   ## Data & Sources
   Download the underlying datasets from the [Observatory data page](/observatory/data/).
   ```

SEO rules: 3–5 internal links, no duplicate H2s, 1200–1800 words, only verified external URLs.

### Step 2 — Push to Draft Branch

After writing the MDX file to disk, create a draft branch and push it:

```bash
cd /home/mathieu/dev/iimv2
git checkout -b draft/[slug]
git add src/content/articles/[slug].mdx
git commit -m "draft: [title]"
git push origin draft/[slug]
```

Then open a GitHub draft PR:
```bash
gh pr create \
  --title "Draft: [title]" \
  --body "Article draft for review. Preview: https://draft-[slug].internetinmyanmar-v2.pages.dev/[slug]/

- [ ] Article text approved
- [ ] Charts render correctly
- [ ] SEO title and meta approved
- [ ] Set draft: false in Keystatic before merging" \
  --head draft/[slug] \
  --base main \
  --draft
```

Cloudflare Pages will build the branch automatically. The preview URL is:
`https://draft-[slug].internetinmyanmar-v2.pages.dev/[slug]/`

(Branch name `draft/[slug]` → CF Pages sanitises `/` to `-` → subdomain `draft-[slug]`.)

### Step 3 — Generate PDF Snapshot

Once the CF Pages preview is live (wait ~90 seconds after push), generate a one-page PDF:

```bash
cd /home/mathieu/dev/iimv2
source agents/venv/bin/activate 2>/dev/null || true
python3 - <<'PYEOF'
from playwright.sync_api import sync_playwright
import time, subprocess, os

SLUG = "[slug]"
PREVIEW_URL = f"https://draft-{SLUG}.internetinmyanmar-v2.pages.dev/{SLUG}/"
PDF_LOCAL = f"/tmp/{SLUG}-snapshot.pdf"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(PREVIEW_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)
    page.pdf(path=PDF_LOCAL, format="A4", print_background=True)
    browser.close()

print(f"PDF saved: {PDF_LOCAL}")

# Upload to R2 for a public temp link
bucket = os.getenv("CF_R2_BUCKET", "iim-media")
key = f"drafts/{SLUG}/article-snapshot.pdf"
subprocess.run([
    "wrangler", "r2", "object", "put",
    f"{bucket}/{key}",
    "--file", PDF_LOCAL,
    "--content-type", "application/pdf",
    "--remote"
], check=True)

pub = os.getenv("CF_R2_PUBLIC_URL", "https://media.internetinmyanmar.com")
print(f"PDF URL: {pub}/{key}")
PYEOF
```

If `playwright` is not installed:
```bash
pip install playwright && playwright install chromium
```

### Step 4 — Share Preview Links

Present the draft package clearly:

```
ARTICLE DRAFT READY FOR REVIEW
════════════════════════════════════════════
Article preview:  https://draft-[slug].internetinmyanmar-v2.pages.dev/[slug]/
PDF snapshot:     https://media.internetinmyanmar.com/drafts/[slug]/article-snapshot.pdf
GitHub PR:        [pr-url]

Preview builds in ~90 s after push. Hard-refresh if you see a 404.

When you're happy with the article, reply:
  "approve article"  → generates social campaign + newsletter draft
  "revise: [notes]"  → edits the MDX and force-pushes the branch
════════════════════════════════════════════
```

**STOP HERE. Wait for Anna's approval before Phase 2.**

---

## PHASE 2 — Social Campaign + Newsletter (after article approval)

Only start Phase 2 when the user explicitly approves the article.

### Step 5 — Social Campaign (shown inline)

Display the full 5-post campaign directly in the conversation for immediate review —
no file needed at this stage. Format it clearly:

```
SOCIAL CAMPAIGN — [Title]
5 posts · 2-week schedule
════════════════════════════════════════════

POST 1 — Day 1 · X
Image: chart-ooni-timeline.png (export from observatory/shutdown-tracker)

[Full tweet text, max 280 chars. Lead with the most surprising stat.
Include article URL. 2–3 hashtags: #Myanmar #InternetFreedom #OONI]

────────────────────────────────────────────

POST 2 — Day 3 · Facebook / LinkedIn
Image: chart-[type].png

[2–3 paragraphs. Focus on one specific data point. Professional tone.
No hashtags on LinkedIn.]

────────────────────────────────────────────

POST 3 — Day 7 · X Thread
Image: chart-[type].png

Tweet 1/3: [hook — the chart finding]
Tweet 2/3: [explain what it shows]
Tweet 3/3: [implication + URL]

────────────────────────────────────────────

POST 4 — Day 10 · LinkedIn
Image: chart-ooni-timeline.png

[Professional angle. What does this mean for press freedom researchers
and journalists covering Myanmar? Include URL.]

────────────────────────────────────────────

POST 5 — Day 14 · X + Facebook
Image: none

[Open data angle. Highlight that the underlying datasets are freely
downloadable. Link to /observatory/data/. Invite researchers to analyse.]

════════════════════════════════════════════
```

After displaying inline, also save to `src/content/articles/[slug]/social-campaign.md`
and commit to the draft branch.

Ask: *"Social posts look good? I'll then draft the newsletter and send to your MailerLite test group."*

### Step 6 — Newsletter Draft + MailerLite Test Send

Generate `src/content/articles/[slug]/newsletter.html` and
`src/content/articles/[slug]/newsletter-meta.txt`, then run the test send:

```bash
cd /home/mathieu/dev/iimv2
source agents/venv/bin/activate 2>/dev/null || true
python3 - <<'PYEOF'
import sys; sys.path.insert(0, 'agents')
from article_packager import generate_newsletter_html, create_and_send_test
from pathlib import Path

SLUG = "[slug]"
TITLE = "[title]"
CATEGORY = "[category]"
EXCERPT = "[excerpt]"
BODY = Path(f"src/content/articles/{SLUG}.mdx").read_text()
ARTICLE_URL = f"https://www.internetinmyanmar.com/{SLUG}/"

html, subject, preview = generate_newsletter_html(TITLE, ARTICLE_URL, CATEGORY, EXCERPT, BODY)
Path(f"src/content/articles/{SLUG}/newsletter.html").write_text(html)
Path(f"src/content/articles/{SLUG}/newsletter-meta.txt").write_text(
    f"Subject: {subject}\nPreview: {preview}"
)

ml_url, sent = create_and_send_test(TITLE, subject, preview, html)
print(f"Subject:  {subject}")
print(f"Preview:  {preview}")
print(f"MailerLite: {ml_url}")
print(f"Test send: {'✓ sent to test group' if sent else 'draft created (not sent)'}")
PYEOF
```

### Step 7 — Final Summary

```
FULL DRAFT PACKAGE READY
════════════════════════════════════════════
Article preview:  https://draft-[slug].internetinmyanmar-v2.pages.dev/[slug]/
PDF snapshot:     https://media.internetinmyanmar.com/drafts/[slug]/article-snapshot.pdf
Newsletter:       sent to MailerLite 'test' group — check your inbox
Social campaign:  shown above (saved to social-campaign.md)
GitHub PR:        [pr-url]

To publish:
  1. Approve the PR → Anna sets draft: false in Keystatic → merge → live in 90 s
  2. Schedule social posts from social-campaign.md
  3. Send newsletter to full list from MailerLite dashboard
════════════════════════════════════════════
```

---

## Revision handling

If the user says `"revise: [notes]"` at any phase:

1. Edit the relevant file(s) based on the notes
2. Commit with `git commit --amend --no-edit` and `git push --force origin draft/[slug]`
3. CF Pages rebuilds the preview automatically (~90 s)
4. Confirm: "Updated — preview rebuilding at [url]"

---

## Hard rules

- `draft: true` always in MDX frontmatter — Anna sets `draft: false` via Keystatic
- Author always `Anna`
- Newsletter only ever sent to `test` group from this skill — never full list
- GitHub PR always a draft — never auto-merged
- No invented URLs in article body — verified links only, or root domain, or omit
- No keyword stuffing anywhere
