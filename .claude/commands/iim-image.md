# /iim-image — Image Upload & MDX Snippet Generator

Handle the full image lifecycle for internetinmyanmar.com articles:
receive image (URL or local path) → SEO rename → upload to Cloudflare R2 → output MDX snippet.

## Arguments

```
/iim-image <source> <article-slug> [descriptor] [n]
```

- `<source>`: URL (`https://...`), absolute local path (`/home/...` or `~/...`), or `chart:<canvas-id>@<page-url>` to screenshot a chart from a live page
- `<article-slug>`: slug of the target article (e.g. `myanmar-election-internet-censorship-2025-2026`)
- `[descriptor]`: optional 1–3 word description for the filename (e.g. `ooni-chart`, `cf-radar-traffic`). If omitted, derive from context.
- `[n]`: optional sequential index (default 1)

## Step-by-step workflow

### Step 1 — Determine R2 config

Check `.env` for:
- `CLOUDFLARE_ACCOUNT_ID`
- `CF_R2_BUCKET` (default: `iim-media` if not set)
- `CF_R2_PUBLIC_URL` (default: `https://media.internetinmyanmar.com` if not set)
- `CF_R2_ACCESS_KEY_ID` and `CF_R2_SECRET_ACCESS_KEY` (for boto3 fallback)

If `CLOUDFLARE_API_TOKEN` is present but the R2-specific keys are not, use `wrangler` CLI (it reads the API token automatically). Check which is available: `which wrangler`.

### Step 2 — Build the SEO filename

Rules:
- Format: `[article-slug]-[descriptor]-[n].[ext]`
- All lowercase, hyphens only, no spaces
- Max 6 words total across slug + descriptor
- If the full slug is long, abbreviate: use only the first 3–4 meaningful words of the slug
- Detect extension from the source (URL path or local file extension). Default to `.jpg` if ambiguous.
- Example: `myanmar-election-ooni-chart-1.jpg`, `myanmar-election-cf-radar-2.png`

### Step 3 — Download, copy, or screenshot the image

If source is a URL:
```bash
curl -L -f -o "/tmp/${SEO_FILENAME}" "${SOURCE_URL}"
```
If source is a local path:
```bash
cp "${SOURCE_PATH}" "/tmp/${SEO_FILENAME}"
```
If source is `chart:<canvas-id>@<page-url>` — screenshot the chart canvas using Playwright, then resize to 1200×630 with dark background padding using sharp:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    page.goto(PAGE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)  # allow Chart.js to render
    el = page.query_selector(f"#{CANVAS_ID}")
    el.screenshot(path="/tmp/chart-raw.png")
    browser.close()
```
Then pad to 1200×630 using sharp (node_modules/sharp in the project root):
```js
const sharp = require('/home/mathieu/dev/iimv2/node_modules/sharp');
// scale to fit, center on #0A1628 background → save as PNG
```
Extension is always `.png` for chart screenshots.

Detect MIME type:
```bash
file --mime-type -b "/tmp/${SEO_FILENAME}"
```

### Step 4 — Upload to Cloudflare R2

**R2 path:** `images/${ARTICLE_SLUG}/${SEO_FILENAME}`

Try `wrangler` first:
```bash
wrangler r2 object put "${CF_R2_BUCKET}/images/${ARTICLE_SLUG}/${SEO_FILENAME}" \
  --file "/tmp/${SEO_FILENAME}" \
  --content-type "${MIME_TYPE}" \
  --remote
```

If wrangler is not available or fails, fall back to the Python uploader:
```bash
python3 agents/utils/r2_uploader.py \
  --file "/tmp/${SEO_FILENAME}" \
  --key "images/${ARTICLE_SLUG}/${SEO_FILENAME}" \
  --content-type "${MIME_TYPE}"
```

Confirm the upload succeeded before proceeding.

### Step 5 — Generate the MDX snippet

**Public URL:** `${CF_R2_PUBLIC_URL}/images/${ARTICLE_SLUG}/${SEO_FILENAME}`

**Generate alt text:** Descriptive, max 10 words, describes what is literally shown in the image. No keyword stuffing. Base it on the descriptor and article context.

**If source is a URL (external image — requires attribution):**
```mdx
<figure>
  <img
    src="https://media.internetinmyanmar.com/images/ARTICLE_SLUG/SEO_FILENAME"
    alt="DESCRIPTIVE ALT TEXT MAX 10 WORDS"
    width="1200"
    height="675"
    loading="lazy"
    decoding="async"
  />
  <figcaption>
    Source: <a href="ORIGINAL_URL" target="_blank" rel="noopener noreferrer">SOURCE_DOMAIN</a>
  </figcaption>
</figure>
```

Extract `SOURCE_DOMAIN` from the URL (e.g. `ooni.org`, `radar.cloudflare.com`).

**If source is a local file (our own asset — no attribution needed):**
```mdx
![DESCRIPTIVE ALT TEXT MAX 10 WORDS](https://media.internetinmyanmar.com/images/ARTICLE_SLUG/SEO_FILENAME)
```

**If it's a featured/hero image (above the fold):**
```mdx
<img
  src="https://media.internetinmyanmar.com/images/ARTICLE_SLUG/SEO_FILENAME"
  alt="DESCRIPTIVE ALT TEXT MAX 10 WORDS"
  width="1200"
  height="675"
  loading="eager"
  fetchpriority="high"
  class="w-full rounded mb-8 aspect-video object-cover"
/>
```

### Step 6 — Output

Print the MDX snippet clearly. Also print:
- Final R2 path
- Public URL
- Suggested frontmatter values if this is a featured image:
  ```yaml
  featuredImage: "https://media.internetinmyanmar.com/images/ARTICLE_SLUG/SEO_FILENAME"
  featuredImageAlt: "DESCRIPTIVE ALT TEXT"
  ```

Do NOT auto-insert into any file. The user pastes the snippet manually.

## SEO rules enforced by this skill

| Rule | Requirement |
|------|-------------|
| Alt text | Descriptive only · max 10 words · zero keyword stuffing |
| Filename | Lowercase · hyphens · max 6 words · article context included |
| Attribution | External images MUST have `<figcaption>` with source link |
| Featured image | Use `loading="eager" fetchpriority="high"` |
| Below-fold images | Use `loading="lazy" decoding="async"` |
| Decorative images | `alt=""` (rare — most IIM images are informational) |

## R2 infrastructure

```
Bucket:     iim-media  (CF_R2_BUCKET env var)
Public URL: https://media.internetinmyanmar.com  (CF_R2_PUBLIC_URL env var)
Path:       images/{article-slug}/{seo-filename}
Region:     auto (Cloudflare R2 is global)
```

The R2 bucket must have public access enabled at the `images/` prefix level via Cloudflare dashboard. If a newly uploaded image returns 403, ask the user to check R2 bucket public access settings.

## Dependencies

- `wrangler` CLI (preferred): `npm i -g wrangler` — authenticates via `CLOUDFLARE_API_TOKEN`
- `curl` or `wget` for URL downloads
- `file` command for MIME detection
- Python fallback: `agents/utils/r2_uploader.py` + `boto3` + `CLOUDFLARE_ACCOUNT_ID`, `CF_R2_ACCESS_KEY_ID`, `CF_R2_SECRET_ACCESS_KEY`

## Example session

```
User: /iim-image https://radar.cloudflare.com/myanmar-traffic-dec2025.png myanmar-election-internet-censorship-2025-2026 cf-radar-traffic 1

Claude Code:
1. SEO filename: myanmar-election-cf-radar-traffic-1.png
2. Downloading from radar.cloudflare.com...
3. MIME: image/png
4. Uploading to R2: iim-media/images/myanmar-election-internet-censorship-2025-2026/myanmar-election-cf-radar-traffic-1.png
5. Upload confirmed ✓

MDX snippet:
---
<figure>
  <img
    src="https://media.internetinmyanmar.com/images/myanmar-election-internet-censorship-2025-2026/myanmar-election-cf-radar-traffic-1.png"
    alt="Cloudflare Radar Myanmar traffic index December 2025"
    width="1200"
    height="675"
    loading="lazy"
    decoding="async"
  />
  <figcaption>
    Source: <a href="https://radar.cloudflare.com/myanmar-traffic-dec2025.png" target="_blank" rel="noopener noreferrer">radar.cloudflare.com</a>
  </figcaption>
</figure>
---

Frontmatter (if featured):
featuredImage: "https://media.internetinmyanmar.com/images/myanmar-election-internet-censorship-2025-2026/myanmar-election-cf-radar-traffic-1.png"
featuredImageAlt: "Cloudflare Radar Myanmar traffic index December 2025"
```
