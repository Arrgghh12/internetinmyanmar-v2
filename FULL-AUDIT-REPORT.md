# Full SEO Audit — internetinmyanmar.com
**Date:** 2026-04-17 | **Stack:** Astro 5, Cloudflare Pages
**Agents:** Technical · Content · Schema · Sitemap · Performance · GEO

---

## Overall SEO Health Score: 48 / 100

| Category | Weight | Score | Weighted |
|---|---|---|---|
| Technical SEO | 22% | 40/100 | 8.8 |
| Content Quality | 23% | 38/100 | 8.7 |
| On-Page SEO | 20% | 55/100 | 11.0 |
| Schema / Structured Data | 10% | 35/100 | 3.5 |
| Performance (CWV) | 10% | 55/100 | 5.5 |
| AI Search Readiness | 10% | 56/100 | 5.6 |
| Images | 5% | 40/100 | 2.0 |
| **Total** | | | **48 / 100** |

---

## Top 5 Critical Issues

1. **168 articles absent from sitemap** — `prerender: false` on `[slug].astro` prevents `@astrojs/sitemap` discovering any article or digest. Google has no sitemap path to content.
2. **NewsArticle schema never emitted** — `Article.astro` inherits only `Organization` schema from `Base.astro`. Every article page is `@type: Organization`. Rich result eligibility: zero.
3. **7 rule-violating articles live in production** — TurnOnVPN guest post under Anna's byline; Russian AI conference PR; 5 travel/speedtest articles. All violate CLAUDE.md hard discard rules.
4. **HSTS max-age=0** — `Strict-Transport-Security: max-age=0; preload` actively removes the site from browser HTTPS enforcement.
5. **Render-blocking Google Fonts via CSS `@import`** — Three families (incl. Noto Sans Myanmar ~1.5–2 MB) loaded on every page. Direct LCP impact: 400–900ms.

## Top 5 Quick Wins

1. Fix HSTS in Cloudflare dashboard (2 min)
2. Set `draft: true` on 7 offending articles (15 min)
3. Generate `og-default.png` 1200×630 — OG image is currently an SVG (rejected by all social platforms)
4. Add `<SchemaOrg type="article" />` call in `Article.astro`
5. Move Google Fonts out of CSS `@import` into `<link>` tags, split Myanmar fonts to `lang="my"` pages only

---

## 1. Technical SEO — 40/100

### CRITICAL

**1.1 Sitemap excludes all articles and digest**
`src/pages/articles/[slug].astro` and `src/pages/digest/[slug].astro` both have `export const prerender = false`. `@astrojs/sitemap` only discovers pre-rendered pages. The sitemap has 27 structural URLs — zero articles, zero digest entries.
Fix: switch `astro.config.mjs` to `output: 'hybrid'`, add `getStaticPaths()` + `export const prerender = true` to both routes.

**1.2 HSTS max-age=0**
Header observed: `strict-transport-security: max-age=0; preload`. This tells browsers to stop enforcing HTTPS and removes the site from the HSTS preload cache.
Fix: Cloudflare → SSL/TLS → Edge Certs → HSTS → set `max-age=31536000`, enable `includeSubDomains`.

**1.3 NewsArticle schema never emitted on article pages**
`Base.astro` hardcodes `<SchemaOrg type="organization" />` on every page. `Article.astro` does not add a `NewsArticle` schema. Despite `SchemaOrg.astro` having full NewsArticle support, it is never called.
Fix: in `Article.astro` add `<SchemaOrg slot="head" type="article" headline={title} datePublished=... authorName="Anna Faure Revol" image={featuredImage ?? siteUrl+'/og-default.png'} ... />`.

### HIGH

**1.4 No hreflang in `<head>`**
Language switcher exists in `<body>` nav but zero `<link rel="alternate" hreflang>` in `<head>`. All four language variants compete as duplicate content.
Fix: loop locales in `Base.astro`, emit hreflang links + `x-default` using existing `getLocalePath()`.

**1.5 OG image is SVG**
`/og-default.svg` — Facebook, Twitter/X, LinkedIn, Slack all reject SVG `og:image`. Default fallback shows no social preview on homepage and all imageless articles.
Fix: generate `/public/og-default.png` 1200×630, update `Base.astro`.

**1.6 Google Fonts render-blocking**
`src/styles/global.css:1` — `@import url('https://fonts.googleapis.com/css2?family=Inter:..&family=Padauk:..&family=Noto+Sans+Myanmar:..')` is render-blocking. Three families loaded on every page regardless of language.
Fix: remove `@import`; load Inter via `<link rel="preload" as="style">` in `Base.astro`; load Padauk + Noto Sans Myanmar only when `lang === 'my'`.

**1.7 Author full name not rendered**
Byline renders "Anna" (first name only). Author bio paragraph is empty. Both damage E-E-A-T.

### MEDIUM

**1.8 No security headers** — No `public/_headers` file. Missing CSP, `X-Frame-Options`, `Referrer-Policy`. Matters for institutional partner credibility (RSF, Freedom House use security scoring tools).

**1.9 Percent-encoded redirect may not match** — `public/_redirects:11` has `/ai-journey-%d0%b0-journey-...`. Cloudflare may normalise encoding before matching. Test with `curl -I`.

**1.10 No IndexNow** — No key file, no submission in `publisher.py`. Instant Bing indexing for new articles.

---

## 2. Content Quality — 38/100

### CRITICAL — Draft immediately (CLAUDE.md rule violations, live in production)

| Slug | Violation |
|---|---|
| `ai-journey-d0-b0-journey-in-the-company-of-a-developer` | Russian AI conference PR. Zero Myanmar connection. Images alt-tagged "Myanmar internet censorship" — keyword stuffing. |
| `impact-myanmar-smart-city-privacy` | TurnOnVPN guest post. Explicitly forbidden in CLAUDE.md. Live under Anna's byline = authorship fraud. |
| `digital-services-travel-myanmar` | Travel guide. Hard discard rule. |
| `yangon-wifi-map` | 2017 WiFi app review. Off-mission. |
| `yangon-internet-tour-airport` | 2016 airport speedtest. Off-mission. |
| `yangon-internet-people-park` | 2016 park speedtest. Off-mission. |
| `yangon-internet-ocean-tamwe` | Same series. Off-mission. |

### HIGH — Thin content / trust violations

| Slug | Problem |
|---|---|
| `technology-in-myanmar-telecom-cybersecurity-blockchain` | ~350 words, AI-generated. Promotes blockchain in 2025 Myanmar with no acknowledgment of the coup. |
| `digital-wallets-myanmar` | ~350 words, AI-generated. Discusses Wave Money/KBZPay as if operating normally post-coup. |
| `how-to-protect-your-online-privacy-in-2023-myanmar` | ~650 words. Undisclosed PureVPN + ExpressVPN affiliate links. Google September 2025 QRG violation. |
| `vpn-myanmar` | Undisclosed PureVPN affiliate link (`billing.purevpn.com/aff.php?aff=38474`). 2018 recommendations, predating junta-era enforcement. |
| `cookie-tv-app-myanmar` | Burmese content tagged `lang: "en"`. Service defunct post-coup. |

### MEDIUM — Stale but recoverable

| Slug | Action |
|---|---|
| `vpn-myanmar` | Full rewrite: post-coup landscape, Tor/Psiphon/Lantern, activist safety warnings |
| `ixp-internet-exchange-myanmar` | Add `updatedAt` + MMIX 2025 status note |
| `internet-myanmar-expensive` | 2016 prices — all operators obsolete |
| `the-economic-cost-of-internet-censorship-in-myanmar-a-call-for-change` | "Call for change to the government" — that government committed the shutdowns. Reframe. |

### MEDIUM — Frontmatter / SEO rule violations

- `seoTitle` ending with "…" stored in frontmatter (multiple articles) — rendered title will be truncated
- `lang: "en"` on Burmese articles: `bypass-country-google-play-store-mm`, `cookie-tv-app-myanmar` need `lang: "my"`
- Duplicate metaDescriptions across EN/Burmese pairs: `fiber-broadband-ftth-myanmar` / `fiber-broadband-ftth-myanmar-my`; `spotify-myanmar` / `how-to-use-spotify-myanmar-my`
- ~35% of articles have `excerpt` as a character-for-character copy of `metaDescription`
- Slug violations: `how-to-protect-your-online-privacy-in-2023-myanmar` (stop words), `the-economic-cost-of-internet-censorship-in-myanmar-a-call-for-change` (9 words)

---

## 3. Schema / Structured Data — 35/100

### Current state
- Homepage: `@type: Organization` ✓ (but weak — see below)
- Article pages: `@type: Organization` only — **NewsArticle never emitted** ✗
- `/about/anna/`: `@type: Person` ✓ but `name: "Anna"` (incomplete) ✗

### Gaps

| Issue | Severity |
|---|---|
| NewsArticle never emitted on article pages | Critical |
| `Organization.sameAs` is `["https://www.internetinmyanmar.com"]` — self-referential, meaningless | High |
| `Organization.logo` missing — required for Google rich results | High |
| `Person.name` is "Anna" — AI entity resolution fails without full name | High |
| No `Person.@id` — cannot link author entity from article schemas | High |
| `NewsArticle.image` undefined when no featuredImage — articles ineligible for rich results | High |
| No `WebSite` schema — no Sitelinks Searchbox eligibility | Medium |
| No `BreadcrumbList` schema — visual breadcrumb not processed by Google | Medium |

### Fixes needed by file

**`SchemaOrg.astro`:** Change to `NewsMediaOrganization`, add `@id: "…/#organization"`, add `logo` ImageObject to `/og-default.png`, remove self-referential `sameAs`, fix `image` to always output ImageObject with fallback, add `isAccessibleForFree: true`, `articleSection`.

**`/about/anna.astro`:** `name: 'Anna Faure Revol'`, add `@id: "…/about/anna/#person"`, `worksFor` referencing `#organization`.

**`Base.astro`:** Add `WebSite` JSON-LD block.

**`Article.astro`:** Add `BreadcrumbList` JSON-LD from existing `primaryCategory` + `categoryHref` vars.

---

## 4. Sitemap — 30/100

| Check | Status |
|---|---|
| Valid XML structure | ✓ |
| Under 50,000 URL limit | ✓ (27 URLs) |
| No deprecated tags | ✓ |
| Article URLs included | ✗ — 168 published articles absent |
| Digest URLs included | ✗ — 121 entries absent |
| `<lastmod>` present | ✗ — no dates on any URL |
| hreflang alternates | ✗ — none generated |

Root cause: `prerender: false` on dynamic routes. Fix: hybrid prerender (see Technical 1.1). After fixing, configure `serialize` option to inject `lastmod` from `updatedAt ?? publishedAt`.

---

## 5. Performance — 55/100

Static code analysis only (PSI quota exhausted; site below CrUX traffic threshold).

| Issue | Metric | Impact |
|---|---|---|
| CSS `@import` Google Fonts — render-blocking | LCP | 400–900ms |
| Fuse.js (~25 kB) bundled on every page | INP/TBT | 25 kB JS off critical path if dynamic import |
| SSR on article pages — Cloudflare Worker cold starts | TTFB/LCP | 50–200ms |
| Featured image `<img>` missing `width`/`height`/`fetchpriority` | CLS | CLS spike risk |
| OG image is SVG | Social | No preview on shares |

**Highest ROI single fix:** move Google Fonts out of `@import`, split Myanmar fonts to `lang="my"` pages only.

---

## 6. GEO / AI Search Readiness — 56/100

| Platform | Score | Key blocker |
|---|---|---|
| Google AI Overviews | 35/100 | No question-headed sections, articles not in sitemap |
| ChatGPT | 40/100 | No full author name in rendered HTML/schema, no Wikipedia entity |
| Perplexity | 55/100 | Good inline citations; benefits from data freshness |
| Bing Copilot | 45/100 | Sitemap gap — articles not systematically discoverable |

### llms.txt issues (`/public/llms.txt` — file exists, returns 200)

| Issue | Severity |
|---|---|
| Author listed as "Anna" not "Anna Faure Revol" | High |
| All URLs are relative (`/observatory/bgp`) — some parsers fail | Medium |
| No `License:` field | Medium |
| No `Contact:` field | Low |

### Author entity inconsistency

"Anna Faure Revol" is in article frontmatter but rendered as "Anna" everywhere in HTML: byline, Person schema, llms.txt, `/about/anna/` page title. AI systems (ChatGPT, Perplexity) cannot build a reliable entity link. Weakens E-E-A-T across all citation platforms.

### Citability strengths

`myanmar-digital-repression-2026` is the strongest citation asset: 59-word opening paragraph, specific statistics with source attribution (RSF, OONI, Freedom House), inline hyperlinked citations.

### Citability gaps

- No question-based H2/H3 headings anywhere on site ("How many websites are blocked in Myanmar?")
- No self-contained answer blocks (134–167 word extractable passages)
- Statistics lack measurement dates ("2,000+ URLs blocked" — as of when?)
- `dateModified` absent on almost all articles

---

## Files Requiring Action

| File | Issues |
|---|---|
| `src/layouts/Article.astro` | Add NewsArticle schema; fix byline to full name; populate bio; add img dimensions + fetchpriority; add BreadcrumbList |
| `src/layouts/Base.astro` | Move Google Fonts to `<link>` tags; split Myanmar fonts; add hreflang; add WebSite schema; fix OG default to .png |
| `src/components/SchemaOrg.astro` | NewsMediaOrganization; add logo; fix sameAs; fix image fallback; add @id throughout |
| `src/styles/global.css` | Remove `@import` Google Fonts |
| `src/pages/articles/[slug].astro` | `prerender = true` + `getStaticPaths()` |
| `src/pages/digest/[slug].astro` | `prerender = true` + `getStaticPaths()` |
| `src/pages/about/anna.astro` | Fix Person schema name and @id |
| `astro.config.mjs` | `output: 'hybrid'`; sitemap lastmod config |
| `public/llms.txt` | Absolute URLs; full author name; License field |
| `public/_headers` | Create: X-Frame-Options, Referrer-Policy, HSTS, CSP |
| 7 article MDX files | `draft: true` |
| `vpn-myanmar.mdx` | Remove/disclose affiliate link |
