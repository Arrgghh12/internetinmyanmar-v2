# Full SEO Audit — internetinmyanmar.com
**Date:** 2026-04-18 | **Plugin:** claude-seo v1.9.0 | **Agents:** 7 specialists

---

## Overall SEO Health Score: 64 / 100

| Category | Weight | Score | Weighted |
|----------|--------|-------|---------|
| Technical SEO | 22% | 72 | 15.8 |
| Content Quality | 23% | 51 | 11.7 |
| On-Page SEO | 20% | 65 | 13.0 |
| Schema / Structured Data | 10% | 55 | 5.5 |
| Performance (CWV) | 10% | 88 | 8.8 |
| AI Search Readiness | 10% | 61 | 6.1 |
| Images | 5% | 60 | 3.0 |

**Previous audit score (2026-04-17): ~48/100 → +16 points** from fixes applied.

---

## Executive Summary

The site has made strong technical progress since the last audit. SSG prerendering, non-blocking fonts, security headers, hreflang, and schema upgrades are all in place. The remaining score gap is concentrated in three areas:

1. **Silent schema drop** — `<slot name="head" />` missing from Base.astro; all Article/BreadcrumbList schema injected by Article.astro is never rendered. Every article page is missing NewsArticle schema.
2. **Content depth** — 40 articles (25%) under 400 words, 11 under 200 words. Author page at 199 words with no last name, no photo, no LinkedIn.
3. **Canonical mismatch** — Migrated articles canonicalize to old WP URL paths (`/slug/` not `/articles/slug/`).

---

## 1. Technical SEO — 72/100

### Crawlability ✅
- robots.txt: `User-agent: * / Allow: /` — correct. All pages indexable.
- Sitemap index at `/sitemap-index.xml` → `/sitemap-0.xml` — 309 URLs, well-formed XML.
- No noindex directives on live content.

### Sitemap
- **309 URLs** confirmed: 163 articles + 121 digest + 25 nav/category pages.
- Articles and digest pages now prerendered and included — fixed from last audit ✅
- **No `<lastmod>` on any URL** (309/309 missing) — low severity for Google, but reduces crawl prioritization signal.
- **3 hex-slug Burmese articles still public** (`/articles/e1-80-*/`). These are opaque to crawlers, carry no keyword value, and are likely legacy "Myanmar Geek" content.

### Security Headers
- `_headers` file present and serving: ✅ X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS declared.
- Note: HSTS in `_headers` is good, but enabling at Cloudflare edge SSL level adds preload eligibility.

### Canonical / URL Structure
- **CRITICAL**: Migrated articles have `originalUrl` set to old WP paths (e.g., `https://www.internetinmyanmar.com/myanmar-internet-censorship/`). Article.astro uses `originalUrl ?? /articles/slug/` as canonical. Result: ~120 migrated articles canonicalize to URLs without the `/articles/` prefix, creating canonical chains once `_redirects` kicks in after DNS cutover.
- New articles (no `originalUrl`) canonicalize correctly to `/articles/slug/`.
- Trailing slash consistency: all 309 sitemap URLs end with `/` — consistent ✅

### Hreflang ✅
- Correctly implemented in Base.astro head for en/fr/es/it with x-default.
- No hreflang in sitemap yet (no translated content exists — correct behavior).

### AI Crawlers in robots.txt
- No explicit per-bot directives. Global `Allow: /` covers all bots implicitly.
- GPTBot, ClaudeBot, PerplexityBot — implicitly allowed but not named.

---

## 2. Content Quality — 51/100

### E-E-A-T Assessment

**Experience: 14/20**
First-person signals in ~62% of articles. Key analytical pieces lack first-hand observations or named sources. `myanmar-digital-repression-2026` is substantive but has zero direct quotes or named contacts.

**Expertise: 17/25**
Author bio page: **199 words**, no photo (placeholder text "Photo"), no last name in schema, no LinkedIn, no external verification path. `seoTitle` is "Anna | Internet in Myanmar" — insufficient for QRG identity verification. Author renders as "By Anna" in all article bylines — single first name not citable by AI systems.

**Authoritativeness: 16/25**
`sources` frontmatter populated on **1 of 161 live articles** only. External citations in only 21% of articles. Organization schema has `sameAs: []` — no external identity links.

**Trustworthiness: 4/10 (weighted: 12/30)**
- No visible contact information without JavaScript.
- No privacy policy page.
- No author photo.
- VPN guide from 2018 has no `updatedAt`, stale notice should be rendering — confirm live.

### Thin Content — CRITICAL
**40 articles (25%) under 400 words:**

| Range | Count | Action |
|-------|-------|--------|
| < 200 words | 11 | Noindex + redirect |
| 200–400 words | 29 | Expand or consolidate |
| 400–800 words | 47 | Flag for editorial |

Worst offenders: `bluewave-promotion-isp` (78 words), `netcore-promotion` (82w), `myanmar-4th-telco-launch-2018` (100w), `telenor-myanmar-4g-six-cities` (118w).

### Content Freshness — HIGH SEVERITY
- **Zero of 169 articles have `updatedAt` set** — no `dateModified` in any schema.
- `vpn-myanmar` — published 2018-04-04, no `updatedAt`, no stale notice (verify live). VPN recommendations from 2018 are potentially harmful. **Direct QRG risk.**
- `myanmar-internet-censorship` — stale notice present but metaDescription opens with COVID-era lede.

### Near-Duplicates
- `bypass-country-google-play-store-mm` and `bypass-country-google-play-store` — likely same content, needs audit.
- `fiber-broadband-ftth-myanmar-my` (382w) and `fiber-broadband-ftth-myanmar` — Burmese/English pair, not linked via `translationOf`.
- No translations implemented yet despite multilingual routing — no duplicate content risk currently.

---

## 3. On-Page SEO — 65/100

### Canonical Issues
- ~120 migrated articles: canonical = old WP URL (see Technical section).
- Article pages: `originalUrl ?? /articles/slug/` logic intentional for migration but needs reversal before DNS cutover.

### Title Tags
- All articles have `seoTitle` — max 60 chars enforced in schema ✅
- Some seoTitles are cut at 60 chars with ellipsis character (`…`) — these should be rewritten.
- `vpn-myanmar` seoTitle: "Why use a VPN in Myanmar" — 24 chars, no primary keyword lead.

### Meta Descriptions
- Present on all articles ✅
- No duplicate metaDescriptions across main content detected.
- `myanmar-internet-censorship` metaDescription opens with "While the COVID outbreak..." — stale for a current SEO description.

### Internal Linking
- Category landing pages exist and link to articles ✅
- Articles have 3–5 internal links per CLAUDE.md spec.
- No FAQ schema on any article — major featured snippet gap.

---

## 4. Schema / Structured Data — 55/100

### Critical Bug: Article Schema Never Renders

**Root cause:** `Article.astro` injects `<SchemaOrg slot="head" />` and `<script type="application/ld+json" slot="head">` for BreadcrumbList, but `Base.astro` has **no `<slot name="head" />`** inside `<head>`. Named slot content is silently dropped by Astro.

**Impact:** Every article page has only 2 JSON-LD blocks (NewsMediaOrganization + WebSite). Zero articles have NewsArticle, author attribution, or BreadcrumbList schema. All schema work in Article.astro is a no-op.

**Fix:** Add `<slot name="head" />` inside `<head>` in Base.astro.

### What's Working
- `NewsMediaOrganization` with `@id`, logo ImageObject, foundingDate, areaServed ✅
- `WebSite` with `@id`, publisher reference ✅
- `@context: "https://schema.org"` (not http) ✅
- Logo is `ImageObject` with width/height ✅

### What's Missing
- **NewsArticle** on all article pages (blocked by slot bug)
- **BreadcrumbList** on all article pages (blocked by slot bug)
- **Person** on `/about/anna/` — schema exists but `sameAs: []`
- **`masthead`** property on NewsMediaOrganization — required for Google News trust
- **`sameAs`** on both Organization and Person — empty arrays
- **`potentialAction`** on WebSite — Sitelinks Searchbox not declared
- **FAQPage** — zero instances across site

---

## 5. Performance — 88/100

### Estimated Core Web Vitals

| Metric | Estimate | Threshold | Status |
|--------|----------|-----------|--------|
| LCP | ~1.2–1.8s | ≤2.5s | ✅ PASS |
| INP | ~50–100ms | ≤200ms | ✅ PASS |
| CLS | ~0.0–0.05 | ≤0.1 | ✅ PASS |

*No CrUX API key — lab estimates only. Add `GOOGLE_API_KEY` for field data.*

### What's Working
- Astro SSG on Cloudflare edge — zero cold-start latency ✅
- LCP candidate is H1 text (no hero image) — best-case scenario ✅
- Non-blocking Google Fonts (media=print swap) ✅
- Fuse.js dynamic import — not in critical path ✅
- Main script bundle: 2.9 KB gzipped ✅

### Issues
1. **CSS bundle 47 KB gzipped** (~190 KB uncompressed) — Tailwind may not be purging all class sources. Target: under 20 KB. Check `tailwind.config.*` content paths.
2. **No `will-change: transform`** on `#ticker-track` — may cause jank on low-end Android devices (primary audience).
3. **Font CLS** — Inter loads via print-swap; adding WOFF2 `<link rel="preload">` for Latin subset would eliminate swap entirely.
4. **Cloudflare beacon** (`static.cloudflareinsights.com/beacon.min.js`, 31 KB, `defer`) — acceptable, cannot be removed if CF analytics used.

---

## 6. AI Search Readiness — 61/100

### Platform Scores

| Platform | Score | Key Gap |
|----------|-------|---------|
| Perplexity | 65/100 | Best — reads llms.txt, SSR content accessible |
| Google AI Overviews | 55/100 | No Article schema; canonical mismatch |
| Bing Copilot | 58/100 | No Article schema; byline truncation |
| ChatGPT | 52/100 | Empty sameAs; no Wikipedia entity |

### llms.txt — GOOD ✅
- Present, absolute URLs, CC BY 4.0 license ✅
- `Editor: Anna` (first name only) — reduces entity disambiguation
- No `Preferred citation:` line
- Only category URLs listed — no individual high-value articles

### Citability Issues
- No structured Sources section rendered in HTML (sources are inline links only)
- Article byline: "By Anna" — not a citable entity for AI models
- Opening paragraphs are scene-setting not direct-answer format
- No FAQ schema on any article

### Canonical mismatch affects AI indexing
Articles with canonical pointing to `/old-slug/` (no `/articles/` prefix) will be indexed under the canonical URL by AI crawlers, not the serving URL.

---

## 7. Images — 60/100

- **OG default is SVG** (`og-default.svg`) — Twitter/OG cards require PNG/JPG. `og:image` tag references `/og-default.png` which returns 404.
- Articles without `featuredImage` use the broken OG default.
- `fetchpriority="high"` on featured images ✅
- `width`/`height` dimensions on featured images ✅
- Alt text audit: most migrated articles have alt texts rewritten ✅ — spot-check confirms descriptive, non-stuffed.

---

## 8. Backlinks — Common Crawl Data

| Metric | Value |
|--------|-------|
| In Common Crawl index | Yes |
| PageRank | 9.62e-9 (rank #5,651,172) |
| Harmonic Centrality | 14,281,715 (rank #3,052,088) |
| Referring domains (sample) | 0 found in latest crawl |
| CC Release | 2026-Jan/Feb/Mar |

Domain is indexed but very low authority in current CC graph. Expected referring domains (RSF, OONI, DVB) not appearing in sample — either not yet in CC or links are too recent. No toxic links detected. No Moz/Bing API data available for DA/PA.

---

## Issues Requiring Action (Ranked by Impact)

### 🔴 CRITICAL

| # | Issue | File |
|---|-------|------|
| C1 | Missing `<slot name="head" />` in Base.astro — all Article/BreadcrumbList schema silently dropped | `src/layouts/Base.astro` |
| C2 | OG default PNG missing — `og:image` returns 404 on articles without featuredImage | `public/og-default.png` |
| C3 | Canonical mismatch on ~120 migrated articles (pointing to old WP URL path) | `src/layouts/Article.astro` |

### 🟠 HIGH

| # | Issue | File |
|---|-------|------|
| H1 | Anna bio page: 199 words, no photo, no LinkedIn, `sameAs: []` | `src/pages/about/anna.astro` |
| H2 | 40 thin articles (<400 words) — 11 under 200 words need noindex/redirect | `src/content/articles/*.mdx` |
| H3 | `vpn-myanmar` 2018 with no stale notice visible — confirm + fix | `src/content/articles/vpn-myanmar.mdx` |
| H4 | 3 hex-slug Burmese articles (`/e1-80-*/`) are public with no SEO value | `src/content/articles/` |
| H5 | `sameAs: []` on Organization and Person schema — no external entity graph | `src/components/SchemaOrg.astro`, anna.astro |
| H6 | All 169 articles missing `updatedAt` — no dateModified signal | `src/content/articles/*.mdx` |

### 🟡 MEDIUM

| # | Issue |
|---|-------|
| M1 | Add `lastmod` to sitemap via serialize callback |
| M2 | Add `masthead` property to NewsMediaOrganization |
| M3 | Add FAQ schema to top 10 articles |
| M4 | Add explicit AI crawler names to robots.txt (GPTBot, PerplexityBot, ClaudeBot) |
| M5 | Add WOFF2 preload for Inter Latin subset (eliminate font CLS) |
| M6 | CSS bundle optimization — verify Tailwind purge coverage |
| M7 | Add `Preferred citation:` and top article URLs to llms.txt |
| M8 | Add `will-change: transform` to ticker animation |
| M9 | Rewrite stale `metaDescription` on `myanmar-internet-censorship` |
| M10 | Mission page: 284 words — expand to 500+ |

### 🟢 LOW

| # | Issue |
|---|-------|
| L1 | Add `potentialAction` (SearchAction) to WebSite schema for Sitelinks Searchbox |
| L2 | Add `inLanguage`, `wordCount`, `isAccessibleForFree` to NewsArticle schema |
| L3 | Create Wikipedia/Wikidata entry for organization, add to `sameAs` |
| L4 | Add `<link rel="alternate" type="application/rss+xml">` to Base.astro head |
