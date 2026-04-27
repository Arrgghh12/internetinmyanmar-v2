# /iim-write — Full Article Production Pipeline

Run the complete article production pipeline for an approved brief:
generates the MDX article, 5-post social campaign, newsletter HTML,
commits everything to a GitHub draft PR, and sends the newsletter to
the MailerLite "test" group for preview.

## Usage

```
/iim-write                                      # pick the latest approved brief automatically
/iim-write <brief-path>                         # specific brief
/iim-write <brief-path> --adjustments "..."    # editor notes passed to the writer
/iim-write <brief-path> --dry-run              # generate locally only, skip GitHub + MailerLite
```

## Step-by-step workflow

### Step 1 — Resolve the brief

If no path argument is given, find the most recently modified file under
`agents/approved/` (any subdirectory, `.md` or `.json`):

```bash
find /home/mathieu/dev/iimv2/agents/approved -type f \( -name "*.md" -o -name "*.json" \) \
  | sort | tail -1
```

If no approved briefs exist, stop and tell the user:
> No approved briefs found in `agents/approved/`. Move a brief from `agents/briefs/` to
> `agents/approved/YYYY-MM-DD/` after Anna approves it, then run `/iim-write` again.

Show the user which brief will be used and ask for confirmation before proceeding.
If `--dry-run` is present, note it upfront.

### Step 2 — Check environment

Verify these keys exist in `.env` (or environment):

| Key | Purpose |
|-----|---------|
| `DEEPSEEK_API_KEY` | Article + social + newsletter generation |
| `GITHUB_TOKEN` | Open draft PR |
| `MAILERLITE_API_TOKEN` | Create campaign + send to test group |
| `MAILERLITE_FROM_EMAIL` | Newsletter from address |
| `MAILERLITE_FROM_NAME` | Newsletter sender name (default: Internet in Myanmar) |

If any key is missing and `--dry-run` is not set, warn the user. With `--dry-run`,
only `DEEPSEEK_API_KEY` is required.

### Step 3 — Run the packager

```bash
cd /home/mathieu/dev/iimv2 && source agents/venv/bin/activate 2>/dev/null || true
python agents/article_packager.py "<brief-path>" [--adjustments "..."] [--dry-run]
```

Stream the output so the user can see progress. The script logs each step:
- Step 1/4: Writing article (DeepSeek — may take 30–60 s)
- Step 2/4: Generating social campaign
- Step 3/4: Generating newsletter HTML
- Step 4/4: Creating MailerLite draft + sending to test group
- Step 5/5: Opening GitHub PR

### Step 4 — Show the review package

After the script completes, summarise what was produced:

```
REVIEW PACKAGE READY
────────────────────────────────────────────
Article preview:        https://www.internetinmyanmar.com/<slug>/
GitHub draft PR:        <pr-url>
Newsletter (MailerLite): sent to 'test' group ✓  |  draft only
Subject:   <subject>
Preview:   <preview-text>

Local files saved:
  src/content/articles/<slug>.mdx
  src/content/articles/<slug>/social-campaign.md
  src/content/articles/<slug>/newsletter.html
  src/content/articles/<slug>/newsletter-meta.txt
────────────────────────────────────────────
Next steps:
  1. Check your inbox for the newsletter preview
  2. Review the PR: <pr-url>
  3. When approved: set draft: false in Keystatic → merge PR → live in 90 s
```

## Article structure (7-section MDX template)

The writer produces articles in this order. If the output deviates, flag it to the user:

1. **Hero** — SEO H1 title + one-sentence subtitle
2. **Lead Insight** — 1–2 paragraphs with the single most surprising finding
3. **Context & Background** — brief history, why this matters now
4. **Data Analysis** — 2–3 `<CensorshipChart>` embeds with surrounding analysis
5. **Key Findings & Implications** — numbered or bulleted conclusions
6. **Methodology & Limitations** — data sources, caveats, probe coverage
7. **Sources & Dataset** — inline source links + download links to `/observatory/data/`

## What gets generated

| Asset | Location | Purpose |
|-------|----------|---------|
| MDX article | `src/content/articles/<slug>.mdx` | Main article (draft: true) |
| Social campaign | `src/content/articles/<slug>/social-campaign.md` | 5-post 2-week schedule |
| Newsletter HTML | `src/content/articles/<slug>/newsletter.html` | MailerLite-ready HTML |
| Newsletter meta | `src/content/articles/<slug>/newsletter-meta.txt` | Subject + preview text |
| GitHub PR | `draft/<slug>` branch | Review checklist with all assets |
| MailerLite draft | MailerLite dashboard | Campaign draft + test send |

## Rules enforced

- `draft: true` is always set — Anna sets `draft: false` via Keystatic before merging
- Author is always `Anna` — never modified by the pipeline
- Newsletter is only sent to the `test` group — never to full subscriber list from this skill
- GitHub PR is always a draft — never auto-merged
- All content goes through Anna's review before publication

## Error handling

| Error | Action |
|-------|--------|
| DEEPSEEK_API_KEY missing | Stop — cannot generate content |
| GITHUB_TOKEN missing | Warn, save files locally, skip PR |
| MAILERLITE_API_TOKEN missing | Warn, save newsletter locally, skip MailerLite |
| Brief not found | Stop, list available briefs in `agents/approved/` |
| writer.py import error | Show the Python traceback, do not retry automatically |

## Adjustments examples

```
/iim-write agents/approved/2026-04-26/myanmar-vpn-blocks.md --adjustments "lead with the Mandalay regional data, not the national average"
/iim-write agents/approved/2026-04-26/myanmar-vpn-blocks.md --adjustments "shorter — target 1000 words, one chart only"
/iim-write agents/approved/2026-04-26/myanmar-vpn-blocks.md --dry-run
```
