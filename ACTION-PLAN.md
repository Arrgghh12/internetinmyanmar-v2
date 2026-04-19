# SEO Action Plan — internetinmyanmar.com
**Generated:** 2026-04-18 | **Score:** 64/100 (+16 from last audit)

---

## CRITICAL — Fix immediately

### C1. Add `<slot name="head" />` to Base.astro — 5 min
**All Article/NewsArticle and BreadcrumbList schema is silently dropped** because Base.astro has no named head slot.

In `src/layouts/Base.astro`, inside `<head>` just before `</head>`:
```astro
<slot name="head" />
```

This one line fixes all article schema on all 161 live articles simultaneously.

### C2. Create og-default.png — 30 min
`og:image` references `/og-default.png` but only `/og-default.svg` exists → 404 on all articles without a featuredImage. Twitter/OG cards broken site-wide.

Install ImageMagick on WSL (`sudo apt install imagemagick`) then:
```bash
convert -size 1200x630 xc:"#08090a" \
  -fill "#7170ff" -font DejaVu-Sans -pointsize 52 \
  -gravity Center -annotate 0 "Internet in Myanmar" \
  public/og-default.png
```
Or create manually at 1200×630 matching the site's dark navy + accent purple.

### C3. Fix canonical on migrated articles — 1 hr
~120 migrated articles have `originalUrl` which Article.astro uses as `canonicalUrl`. After DNS cutover this creates a canonical loop (canonical → 301 → same page).

**Decision required:** Choose one of:
- **Option A (recommended):** Remove `originalUrl` from `canonicalUrl` logic in `Article.astro`. Let canonical always be `/articles/slug/`. The `_redirects` file handles old URL traffic. Add `originalUrl` as a plain `<link rel="original">` meta if needed for reference.
- **Option B:** Clear `originalUrl` from all migrated article frontmatter (bulk sed).

Change in `src/layouts/Article.astro`:
```astro
// Before:
const canonicalUrl = originalUrl ?? new URL(`/articles/${slug}/`, Astro.site).href

// After:
const canonicalUrl = new URL(`/articles/${slug}/`, Astro.site).href
```

---

## HIGH — Fix this week

### H1. Expand Anna bio page — 2 hrs editorial
Current state: 199 words, no photo, no last name visible in schema, `sameAs: []`.

Required for QRG trust threshold:
- Expand to 600+ words: publication history, named affiliations (RSF connections, OONI collaborations), areas covered, methodology
- Add a real photo (removes "Photo" placeholder text)
- Add LinkedIn URL to Person schema `sameAs` array
- Add `jobTitle: "Editor-in-Chief"` and `description` to Person schema
- seoTitle: "Anna — Editor, Internet in Myanmar" → something with more identity signal

**Note:** Schema still shows `name: "Anna"`. The privacy decision (first name only in public code) means AI citation will use "Anna" — acceptable but limits disambiguability.

### H2. Triage 40 thin articles — 2 hrs
```bash
# Find articles under 400 words (rough count by file size):
for f in src/content/articles/*.mdx; do
  words=$(wc -w < "$f")
  [ "$words" -lt 400 ] && echo "$words $f"
done | sort -n | head -20
```

Actions:
- **Under 200 words (11 articles):** Set `draft: true`, add 301 redirect to category page in `_redirects`
- **200–400 words (29 articles):** Add to editorial backlog for expansion or consolidation

### H3. Draft 3 hex-slug Burmese articles — 5 min
Articles at `/articles/e1-80-*/` are published with opaque hex slugs, no SEO value, likely legacy Myanmar Geek content.

```bash
# Draft all three:
for slug in \
  "e1-80-80-e1-80-bc-e1-80-ba-e1-80-94-e1-80-b9-e1-80-b1-e1-80-90-e1-80-ac-e1-80-b9" \
  "e1-80-9a-e1-80-b1-e1-80-94-e1-82-94-e1-80-b1-e1-80-81-e1-80-90-e1-80-b9-e1-80-9c" \
  "e1-80-90-e1-80-85-e1-80-b9-e1-80-85-e1-80-91-e1-80-80-e1-80-b9-e1-80-90-e1-80-85"; do
  sed -i 's/^draft: false/draft: true/' "src/content/articles/${slug}.mdx"
done
```

### H4. Add `updatedAt` to stale evergreen articles — editorial
Priority articles to update and set `updatedAt: 2026-04-18`:
- `vpn-myanmar` — 2018, VPN landscape has changed entirely
- `myanmar-internet-censorship` — 2020 COVID lede, needs refresh
- `ixp-internet-exchange-myanmar` — infrastructure article
- `internet-myanmar-expensive` — pricing data stale

Also: verify `vpn-myanmar` stale notice is rendering on live page (should be — published 2018, threshold is 18 months).

### H5. Populate `sameAs` arrays — 30 min
In `src/components/SchemaOrg.astro` and `src/pages/about/anna.astro`:

For Organization:
```json
"sameAs": [
  "https://www.linkedin.com/company/internet-in-myanmar",
  "https://twitter.com/IIMyanmar"
]
```
(add only URLs that actually exist)

For Person — once LinkedIn confirmed:
```json
"sameAs": ["https://www.linkedin.com/in/anna-[slug]"]
```

---

## MEDIUM — Within 1 month

### M1. Add AI crawler directives to robots.txt — 10 min
`public/robots.txt`:
```
User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: *
Allow: /
```

### M2. Add `masthead` to NewsMediaOrganization schema — 10 min
Required for Google News publisher trust:
```json
"masthead": "https://www.internetinmyanmar.com/about/mission/"
```

### M3. Add FAQ schema to top articles — 2 hrs
Start with `vpn-myanmar`, `myanmar-internet-censorship`, `myanmar-digital-repression-2026`.
Map existing question-format H2s to FAQPage JSON-LD entries.

### M4. Add WOFF2 preload for Inter — 15 min
Extract the Inter Latin WOFF2 URL from the Google Fonts CSS response and add to Base.astro head:
```html
<link rel="preload" as="font" type="font/woff2"
  href="https://fonts.gstatic.com/s/inter/v13/[hash].woff2"
  crossorigin>
```

### M5. Add `will-change: transform` to ticker — 5 min
In homepage CSS or global.css:
```css
#ticker-track { will-change: transform; }
```

### M6. Add `lastmod` to sitemap — 1 hr
In `astro.config.mjs` sitemap integration, add a post-build script that patches `dist/sitemap-0.xml` with `<lastmod>` dates read from article frontmatter `publishedAt` values.

### M7. Extend llms.txt — 20 min
Add `Preferred citation:` line and 5–10 highest-value article URLs:
```
> Preferred citation: Internet in Myanmar (internetinmyanmar.com)
```
Then add an `## Key Articles` section with absolute URLs to flagship pieces.

### M8. Rewrite stale metaDescriptions — 30 min
Priority: `myanmar-internet-censorship` (COVID-era lede), `vpn-myanmar` (2018 framing).

### M9. Expand Mission page — editorial
Current: 284 words. Target: 500+ with methodology section and data sources explanation.

---

## LOW — Backlog

- **L1.** Add `potentialAction` SearchAction to WebSite schema (Sitelinks Searchbox)
- **L2.** Create Wikipedia/Wikidata entry for "Internet in Myanmar", add to `sameAs`
- **L3.** Add `<link rel="alternate" type="application/rss+xml">` to Base.astro head
- **L4.** Self-host Inter font to eliminate Google Fonts DNS lookup
- **L5.** CSS bundle audit — verify Tailwind content paths purging all sources (target <20 KB gz)
- **L6.** Add `inLanguage`, `wordCount`, `isAccessibleForFree` to NewsArticle schema

---

## Sprint Order

| Today (1 hr) | This week | This month | Backlog |
|---|---|---|---|
| C1 — head slot fix | C2 — OG PNG | M1 AI crawlers | L1–L6 |
| C3 — canonical fix | H1 — Anna bio | M2 masthead | |
| H3 — hex slug draft | H2 — thin content | M3 FAQ schema | |
| | H4 — updatedAt | M4–M9 | |
| | H5 — sameAs | | |
