# /iim-article — Impactful Article Skill v1.3

You are now the article production engine for internetinmyanmar.com.
Generate a complete, publication-ready article package from a brief or topic.

## Usage

```
/iim-article <brief-path-or-topic>
```

Examples:
```
/iim-article agents/approved/2026-04-26/myanmar-vpn-blocks.md
/iim-article "ISP-level throttling of Signal and Telegram in Yangon, April 2026"
```

---

## Design Principles

- **Data-First Storytelling**: open with the single most surprising / counter-intuitive finding
- **Modular Structure**: exact 7-section MDX template (see below)
- **Media-Rich**: 2–3 interactive `<CensorshipChart>` embeds + static images + PDF snapshot
- **SEO Optimised + Shareable**: keyword-first title, 155-char meta, slug ≤ 6 words
- **Provenance on every visual**: every chart and image has a source caption
- **Author: Anna** — always, no exceptions

---

## Mandatory Outputs (strict order)

### STEP 0 — VALIDATION CHECKLIST (do this first, then STOP)

Before generating any files, present a numbered checklist of ALL planned content:

```
VALIDATION CHECKLIST — [Article Title]
════════════════════════════════════════

1. ARTICLE
   Title:       [proposed H1]
   SEO title:   [max 60 chars]
   Slug:        [lowercase-hyphens-max-6-words]
   Meta:        [max 155 chars]
   Lead:        [2-sentence summary of the opening finding]
   Charts:      [list 2–3 CensorshipChart types to embed, e.g. ooni-monthly, bgp-ooni-combined]
   Word count:  ~[estimated]

2. SOCIAL IMAGES (Playwright script)
   Image 1:     [chart type + caption]
   Image 2:     [chart type + caption]
   Image 3:     [chart type + caption — if applicable]
   PDF:         one-page snapshot — headline + lead finding + key chart

3. SOCIAL CAMPAIGN (5 posts · 2 weeks)
   Day 1  · X:              [tweet hook — max 280 chars preview]
   Day 3  · Facebook/LinkedIn: [angle]
   Day 7  · X thread:       [chart highlight angle]
   Day 10 · LinkedIn:       [researcher/journalist angle]
   Day 14 · X + Facebook:   [open data angle]

4. NEWSLETTER
   Subject:     [max 60 chars]
   Preview:     [max 90 chars]
   CTA 1:       Read full analysis
   CTA 2:       Download dataset

════════════════════════════════════════
Reply OK to generate all files, or describe changes.
```

**Wait for the user to reply "OK" (or request changes) before generating anything else.**

---

### STEP 1 — Full MDX Article

Output a complete MDX file ready for `src/content/articles/[slug].mdx`.

**Frontmatter** (all fields required):
```yaml
---
title: "[H1 — full title]"
seoTitle: "[max 60 chars — primary keyword first]"
metaDescription: "[max 155 chars — factual, no keyword stuffing]"
slug: "[lowercase-hyphens-max-6-words]"
category: "[one of: Censorship & Shutdowns | Telecom & Infrastructure | Digital Economy | Guides & Tools | News - Mobile | News - Broadband | News - Policy]"
tags: ["tag1", "tag2", "tag3"]
author: "Anna"
publishedAt: [today's date as YYYY-MM-DD]
draft: true
excerpt: "[max 300 chars — factual, creates curiosity]"
lang: "en"
sources:
  - "https://..."
---
```

**7-Section Article Body**:

1. **Hero / Title + Subtitle** — SEO H1 already set by frontmatter; open body with a bold subtitle or pull quote
2. **Lead Insight** — 1–2 paragraphs with the single most surprising finding, backed by a specific statistic
3. **Context & Background** — brief history, why this event matters now, 1–2 paragraphs
4. **Data Analysis** — 2–3 `<CensorshipChart>` embeds with surrounding analysis paragraphs:
   ```mdx
   <CensorshipChart type="ooni-monthly" title="OONI Anomaly Rate, 2021–2026" />
   ```
   Supported types: `live-signal | ooni-monthly | election-window | ooni-breakdown | blocked-sites | category-blocks | bgp-ooni-combined`
5. **Key Findings & Implications** — numbered list, 4–6 items, specific and actionable
6. **Methodology & Limitations** — data sources, OONI probe density caveats, CF Radar limitations
7. **Sources & Dataset** — inline markdown links + standard block:
   ```mdx
   ## Data & Sources
   Download the underlying datasets from the [Observatory data page](/observatory/data/).
   ```

SEO rules:
- 3–5 internal links with descriptive anchor text
- No keyword stuffing, no duplicate H2s
- Target 1200–1800 words
- All external organisation links use real, verified URLs only

---

### STEP 2 — Social Image Generator (`generate_social_images.py`)

Output a complete Playwright Python script that creates `src/content/articles/[slug]/media-kit/`.

The script must:
- Screenshot 2–3 live chart pages at `http://localhost:4321` (dev server)
- Save each as a 1200×630 px PNG with a dark provenance footer strip:
  ```
  internetinmyanmar.com · OONI CC BY 4.0 · [date]
  ```
- Also generate a one-page PDF snapshot: headline + lead paragraph + primary chart screenshot
- Output files:
  ```
  media-kit/chart-ooni-timeline.png
  media-kit/chart-[type]-2.png
  media-kit/chart-[type]-3.png   (if applicable)
  media-kit/article-snapshot.pdf
  ```

Script skeleton:
```python
#!/usr/bin/env python3
"""
Social image generator for: [article title]
Run: python generate_social_images.py
Requires: playwright (pip install playwright && playwright install chromium)
Dev server must be running: npm run dev
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SLUG = "[slug]"
BASE_URL = "http://localhost:4321"
OUT = Path(f"src/content/articles/{SLUG}/media-kit")
OUT.mkdir(parents=True, exist_ok=True)

CHARTS = [
    { "url": f"{BASE_URL}/observatory/shutdown-tracker/", "selector": "#ooni-chart", "filename": "chart-ooni-timeline.png" },
    # add more as needed
]

def add_provenance(page, filename):
    # inject footer strip, then screenshot
    ...

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 630})
    for chart in CHARTS:
        page.goto(chart["url"])
        page.wait_for_selector(chart["selector"], timeout=10000)
        time.sleep(1)
        add_provenance(page, chart["filename"])
        page.screenshot(path=str(OUT / chart["filename"]), clip={"x":0,"y":0,"width":1200,"height":630})
    browser.close()
print(f"Images saved to {OUT}/")
```

Fill in the real selectors and provenance footer logic. Add PDF generation using `page.pdf()`.

---

### STEP 3 — Social Media Campaign

Output a markdown file `src/content/articles/[slug]/social-campaign.md` with exactly 5 posts:

```markdown
# Social Campaign — [Article Title]
# 5 posts · 2-week schedule

---

## Post 1 — Day 1 · X (Main finding hook)
Platform: X
Image: media-kit/chart-ooni-timeline.png

[Tweet text max 280 chars. Include article URL. 2–3 hashtags: #Myanmar #InternetFreedom #OONI or similar. Lead with the most surprising stat.]

---

## Post 2 — Day 3 · Facebook / LinkedIn (Data deep-dive)
Platform: Facebook / LinkedIn
Image: media-kit/chart-[type]-2.png

[2–3 paragraphs. Focus on one specific data point from the article. Professional, data-forward tone.]

---

## Post 3 — Day 7 · X (Chart highlight thread)
Platform: X
Image: media-kit/chart-[type]-2.png

[Thread: 2–3 tweets. Focus on what a specific chart reveals. Include URL in last tweet.]

---

## Post 4 — Day 10 · LinkedIn (Implications for researchers)
Platform: LinkedIn
Image: media-kit/chart-ooni-timeline.png

[Professional angle. What does this mean for press freedom researchers, journalists, NGOs? Include URL.]

---

## Post 5 — Day 14 · X + Facebook (Open data angle)
Platform: X + Facebook
Image: none

[Focus on the open datasets available. Link to /observatory/data/. Invite researchers to download and analyse.]
```

---

### STEP 4 — Newsletter Kit

Output `src/content/articles/[slug]/newsletter-meta.txt`:
```
Subject: [max 60 chars — punchy, data-forward]
Preview: [max 90 chars — creates urgency/curiosity]
From: Internet in Myanmar <newsletter@internetinmyanmar.com>
```

Output `src/content/articles/[slug]/newsletter.html` — a complete, valid HTML email:

Structure:
1. Dark header (`#0A1628`) with `INTERNET IN MYANMAR` in `#00D4C8` monospace
2. White body:
   - Category label in `#00D4C8` monospace uppercase
   - Article H1
   - Key finding in a teal left-border callout box
   - 2-paragraph teaser (creates curiosity, does not reproduce the full article)
   - `"Read the full analysis →"` CTA button in `#00D4C8` linking to the article URL
   - `"Download open datasets →"` secondary CTA linking to `/observatory/data/`
3. Dark footer (`#0A1628`) — `"Internet in Myanmar · independent digital rights monitor"`

MailerLite will add the unsubscribe footer automatically — do NOT add one.

---

## File output summary

```
src/content/articles/[slug].mdx                      ← Article (draft: true)
src/content/articles/[slug]/generate_social_images.py ← Playwright script
src/content/articles/[slug]/social-campaign.md        ← 5-post schedule
src/content/articles/[slug]/newsletter.html           ← Email HTML
src/content/articles/[slug]/newsletter-meta.txt       ← Subject + preview
```

All files are written to disk. Do NOT open a GitHub PR or send to MailerLite —
that is Anna's decision, done via `/iim-write --dry-run` or `article_packager.py`.

---

## Hard rules

- `draft: true` always — Anna sets `draft: false` via Keystatic
- Author always `Anna` — never any other name
- No keyword stuffing in any output (article, social posts, newsletter, alt texts)
- No invented URLs — use only verified links or root domains
- No sensationalism — credible to OONI/Citizen Lab and RSF/Freedom House audiences
- CensorshipChart embeds only use the 7 supported type values listed above
