# /iim-article — Impactful Article Skill v2.1

Two-phase article production: draft article first → Anna approves online →
then social campaign + newsletter. Nothing merges, nothing sends without approval.

## Reference standard

Before writing any article, review `src/content/articles/myanmar-election-internet-censorship-2025-2026.mdx`.
That article is the quality and depth benchmark. Match it.

Key traits to match:
- Specific data throughout: exact percentages, exact dates, exact counts — no vague ranges
- Bold opening pull-quote = the single most surprising or counterintuitive finding
- Section headers are substantive phrases, not generic labels ("A Coup's Electoral Legitimation" not "Background")
- The absence of an expected signal is treated as a finding when data supports it
- Every data limitation is stated explicitly and does not hedge the findings that the data does support
- ~1,800–2,500 words in the body

---

## Usage

```
/iim-article <brief-path-or-topic>
/iim-article agents/approved/2026-04-26/myanmar-vpn-blocks.md
/iim-article "ISP throttling of Signal in Yangon, April 2026"
```

---

## Design Principles

- Data-first: open with the single most surprising finding — the one that reframes the story
- Specific chart component imports (not the generic wrapper — see Charts section below)
- Author: Anna — always, no exceptions
- Nothing publishes without Anna's explicit approval

---

## PHASE 1 — Draft Article + Online Preview

### Step 0 — Validation Checklist (stop and wait for OK)

Before writing anything, present this checklist:

```
ARTICLE DRAFT PLAN — [Title]
══════════════════════════════════════
Slug:        [filename only — no frontmatter field]
SEO title:   [max 60 chars — primary keyword first]
Meta:        [max 155 chars — factual, light CTA, no stuffing]
Categories:  [1–2 from valid list]
Lead:        [the single most surprising finding — 1 sentence]
Charts:      [specific component names, e.g. LiveSignalChart, OoniBreakdownChart]
Word count:  ~[estimate — target 1,800–2,500]
Angle note:  [why this framing, what makes it non-obvious]
══════════════════════════════════════
Reply OK to write the article, or describe changes.
```

Wait for OK before continuing.

### Step 1 — Write the MDX Article

Write the full MDX file to disk at `src/content/articles/[slug].mdx`.

**Frontmatter** (all fields required, `draft: true` always):
```yaml
---
title: "[full title]"
seoTitle: "[max 60 chars — primary keyword first]"
metaDescription: "[max 155 chars — factual, no stuffing]"
categories:
  - "[Censorship & Shutdowns | VPN & Security | ISP & Broadband | Mobile & Data Plans | Telecom & Infrastructure | Digital Services | Policy & Regulation]"
tags:
  - "tag1"
  - "tag2"
author: "Anna"
publishedAt: YYYY-MM-DD
draft: true
excerpt: "[max 300 chars]"
readingTime: [estimated minutes, integer]
lang: "en"
sources:
  - "https://..."
---
```

**IMPORTANT — frontmatter rules:**
- `categories` is an **array**, not a string. Valid values exactly: `Censorship & Shutdowns`, `VPN & Security`, `ISP & Broadband`, `Mobile & Data Plans`, `Telecom & Infrastructure`, `Digital Services`, `Policy & Regulation`
- There is **no `slug` field** in frontmatter — the slug is derived from the filename
- `metaDescription` max 155 characters — validate before writing
- `seoTitle` max 60 characters — validate before writing

**Chart component imports** — place immediately after the closing `---` of frontmatter:
```mdx
import LiveSignalChart from '../../components/charts/LiveSignalChart.astro'
import OoniBreakdownChart from '../../components/charts/OoniBreakdownChart.astro'
import BlockedSitesChart from '../../components/charts/BlockedSitesChart.astro'
```

Available chart components and what they show:
| Component | Data | Use when |
|---|---|---|
| `LiveSignalChart` | OONI daily + CF Radar daily, last 30 days | Current conditions, any recent-event article |
| `OoniBreakdownChart` | OONI weekly, last 26 weeks | 6-month trend, measurement volume |
| `BlockedSitesChart` | Per-domain anomaly rates | Censorship scope, specific platform blocking |
| `ElectionTimelineChart` | OONI monthly 2021–present | Multi-year trend, longitudinal analysis |
| `ElectionWindowChart` | CF Radar weekly, election window | Traffic-layer analysis, ISP routing changes |
| `CategoryBlockChart` | OONI anomaly by category | Thematic breakdown (news vs. VPN vs. social) |

Use the specific component, not the generic `CensorshipChart` wrapper.

**7-Section Body structure:**

1. **Bold pull-quote** — single sentence, the most surprising or counterintuitive finding. Set in `**bold**`. This is the first thing a reader sees.

2. **Lead paragraphs** — 2–3 paragraphs. Why this story now? What is the analytical hook? State the central finding with a precise statistic. Do not bury the lead.

3. **Context** — subsection (H2) with a substantive title, not "Background". 1–2 paragraphs. The history that explains why this finding matters.

4. **Data Analysis** — 2–3 subsections, each opening with a chart component followed by analytical prose:
   ```mdx
   <LiveSignalChart />
   
   The chart shows...
   ```
   Every chart gets at least two paragraphs of specific analysis. Cite the specific numbers visible in the chart. State what the chart cannot show and why.

5. **The Model: [Name]** — when the data supports a conceptual thesis, name it explicitly. Use this section to frame the overarching pattern the individual findings reveal. Example from the reference: "The Model: Ambient Censorship vs. Emergency Shutdown."

6. **Key Findings** — 5–7 numbered findings. Each is specific and actionable: a percentage, a named entity, a date, a causal claim that the data supports. No vague generalisations.

7. **What Comes Next** — 2–3 paragraphs on near-term implications, indicators to watch, or upcoming events that will test the pattern. Add when there is clear forward-looking context.

8. **Methodology & Limitations** — one paragraph per data source. State what the source measures, how we process it, and its specific limitations. Do not omit limitations; they strengthen credibility.

9. **Researcher Data Downloads** — standard table, always include for data-driven articles:
   ```mdx
   | Dataset | Format | Description |
   |---|---|---|
   | [OONI Timeseries](/data/ooni_timeseries.csv) | CSV | Monthly anomaly rates, February 2021 – present |
   | [Blocked Sites Database](/data/blocked_sites.csv) | CSV | Confirmed blocked domains with anomaly rates |
   | [Verified Shutdowns](/data/keepiton_shutdowns.csv) | CSV | KeepItOn-verified shutdown events, normalized |
   | [Unified Events](/data/unified_events.json) | JSON | All sources merged and cross-validated |
   ```

10. **Data & Sources footer**:
    ```mdx
    ## Data & Sources
    Download the underlying datasets from the [Observatory data page](/observatory/data/).
    ```

**SEO rules:** 4–6 internal links, no duplicate H2s, 1,800–2,500 words, only verified external URLs — no invented links.

**Data precision rules:**
- Always use exact figures when available from our pipeline: `13.4%` not "around 13%"
- Name specific laws, organizations, dates: "the 2025 Cybersecurity Law" not "new legislation"
- Cite the source of every external statistic inline the first time
- State data gaps explicitly: "our BGP monitoring began April 2026 and cannot retroactively analyse..." is correct; silently omitting the gap is not

---

### Optional Sections

**A. PDF download block** — when the article is a major investigative piece:
```mdx
## Download the Report (PDF)

[Download the full report as PDF](https://media.internetinmyanmar.com/data/[slug]/[slug]-report.pdf) — optimised for print and citation.
```

---

### Step 2 — Push to Draft Branch

After writing the MDX file to disk, create a draft branch and push it:

```bash
cd /home/mathieu/dev/iimv2
git stash && git pull --rebase origin main && git stash pop
git checkout -b draft/[slug]
git add src/content/articles/[slug].mdx
git commit -m "draft: [title]"
git push origin draft/[slug]
```

Then open a GitHub draft PR (if `gh` CLI is available):
```bash
gh pr create \
  --title "Draft: [title]" \
  --body "Article draft for review. Preview: https://draft-[slug].internetinmyanmar-v2.pages.dev/articles/[slug]/

- [ ] Article text approved
- [ ] Charts render correctly
- [ ] SEO title and meta approved
- [ ] Set draft: false in Keystatic before merging" \
  --head draft/[slug] \
  --base main \
  --draft
```

If `gh` is not available, print the GitHub URL from the push output for the user to open manually.

Cloudflare Pages will build the branch automatically. The preview URL is:
`https://draft-[slug].internetinmyanmar-v2.pages.dev/articles/[slug]/`

(Branch name `draft/[slug]` → CF Pages sanitises `/` to `-` → subdomain `draft-[slug]`.)

### Step 3 — Generate PDF Snapshot

Once the CF Pages preview is live (wait ~90 seconds after push), generate a PDF:

```bash
cd /home/mathieu/dev/iimv2
source agents/venv/bin/activate 2>/dev/null || true
python3 - <<'PYEOF'
from playwright.sync_api import sync_playwright
import time, subprocess, os

SLUG = "[slug]"
PREVIEW_URL = f"https://draft-{SLUG}.internetinmyanmar-v2.pages.dev/articles/{SLUG}/"
PDF_LOCAL = f"/tmp/{SLUG}-snapshot.pdf"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(PREVIEW_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)
    page.pdf(path=PDF_LOCAL, format="A4", print_background=True)
    browser.close()

print(f"PDF saved: {PDF_LOCAL}")

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

```
ARTICLE DRAFT READY FOR REVIEW
════════════════════════════════════════════
Article preview:  https://draft-[slug].internetinmyanmar-v2.pages.dev/articles/[slug]/
PDF snapshot:     https://media.internetinmyanmar.com/drafts/[slug]/article-snapshot.pdf
GitHub PR:        [pr-url or "open manually: [github-url]"]

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

Display the full 5-post campaign directly in the conversation for immediate review.

```
SOCIAL CAMPAIGN — [Title]
5 posts · 2-week schedule
════════════════════════════════════════════

POST 1 — Day 1 · X
Image: [chart export from observatory]

[Full tweet text, max 280 chars. Lead with the most surprising stat.
Include article URL. 2–3 hashtags: #Myanmar #InternetFreedom #OONI]

────────────────────────────────────────────

POST 2 — Day 3 · Facebook / LinkedIn
Image: [chart name]

[2–3 paragraphs. Focus on one specific data point. Professional tone.
No hashtags on LinkedIn. Include article URL.]

────────────────────────────────────────────

POST 3 — Day 7 · X Thread
Image: [chart name]

Tweet 1/3: [hook — the chart finding]
Tweet 2/3: [explain what it shows]
Tweet 3/3: [implication + URL]

────────────────────────────────────────────

POST 4 — Day 10 · LinkedIn
Image: [chart name]

[Professional angle. What does this mean for press freedom researchers
and journalists covering Myanmar? Include URL.]

────────────────────────────────────────────

POST 5 — Day 14 · X + Facebook
Image: none

[Open data angle. The underlying datasets are freely downloadable.
Link to /observatory/data/. Invite researchers to analyse.]

════════════════════════════════════════════
```

After displaying inline, save to `src/content/articles/[slug]/social-campaign.md` and commit to the draft branch.

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
ARTICLE_URL = f"https://www.internetinmyanmar.com/articles/{SLUG}/"

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
Article preview:  https://draft-[slug].internetinmyanmar-v2.pages.dev/articles/[slug]/
PDF snapshot:     https://media.internetinmyanmar.com/drafts/[slug]/article-snapshot.pdf
Newsletter:       sent to MailerLite 'test' group — check your inbox
Social campaign:  shown above (saved to social-campaign.md)
GitHub PR:        [pr-url]

To publish:
  1. Anna sets draft: false in Keystatic → merge PR → live in 90 s
  2. Schedule social posts from social-campaign.md
  3. Send newsletter to full list from MailerLite dashboard
════════════════════════════════════════════
```

---

## Revision handling

If the user says `"revise: [notes]"` at any phase:

1. Edit the relevant file(s) based on the notes
2. `git add` + `git commit --amend --no-edit` + `git push --force origin draft/[slug]`
3. CF Pages rebuilds automatically (~90 s)
4. Confirm: "Updated — preview rebuilding at [url]"

---

## Hard rules

- `draft: true` always in MDX frontmatter — Anna sets `draft: false` via Keystatic
- Author always `Anna`
- Newsletter only ever sent to `test` group — never full list
- GitHub PR always a draft — never auto-merged
- No invented URLs — verified links only, or root domain, or omit
- No keyword stuffing anywhere
- `categories` is an array — never a single string
- `metaDescription` max 155 chars — always validate before writing
- Always `git stash && git pull --rebase origin main && git stash pop` before creating a new branch
