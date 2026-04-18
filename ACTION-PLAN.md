# SEO Action Plan — internetinmyanmar.com
**Generated:** 2026-04-17 | **Based on:** 6-agent audit (Technical · Content · Schema · Sitemap · Performance · GEO)

---

## CRITICAL — Fix before DNS cutover

### C1. Draft 7 rule-violating articles — 15 min
Set `draft: true` in frontmatter on:
- `ai-journey-d0-b0-journey-in-the-company-of-a-developer.mdx`
- `impact-myanmar-smart-city-privacy.mdx` ← TurnOnVPN guest post under Anna's byline
- `digital-services-travel-myanmar.mdx`
- `yangon-wifi-map.mdx`
- `yangon-internet-tour-airport.mdx`
- `yangon-internet-people-park.mdx`
- `yangon-internet-ocean-tamwe.mdx`

### C2. Fix sitemap — include all articles + digest — 2–4 hrs
`astro.config.mjs` → `output: 'hybrid'`. Add `getStaticPaths()` + `export const prerender = true` to `src/pages/articles/[slug].astro` and `src/pages/digest/[slug].astro`. Without this, 168 articles and 121 digest entries are invisible to Google's bulk indexing.

### C3. Emit NewsArticle schema on article pages — 30 min
In `src/layouts/Article.astro`, add to head slot:
```astro
<SchemaOrg
  type="article"
  headline={title}
  datePublished={publishedAt.toISOString()}
  dateModified={(updatedAt ?? publishedAt).toISOString()}
  authorName="Anna Faure Revol"
  authorUrl={`${siteUrl}/about/anna/`}
  image={featuredImage ?? `${siteUrl}/og-default.png`}
  url={canonicalUrl}
  description={metaDescription}
  articleSection={primaryCategory}
/>
```

### C4. Fix HSTS — 2 min
Cloudflare dashboard → SSL/TLS → Edge Certificates → HSTS → `max-age=31536000`, `includeSubDomains` on.

### C5. Remove/disclose affiliate link in vpn-myanmar.mdx — 10 min
Remove `billing.purevpn.com/aff.php?aff=38474` or add explicit disclosure notice. Google September 2025 QRG violation.

---

## HIGH — Fix within 1 week

### H1. Move Google Fonts out of CSS @import — 1 hr
**LCP impact: 400–900ms improvement**

`src/styles/global.css`: remove the `@import` line entirely.

`src/layouts/Base.astro` `<head>`:
```html
<link rel="preload" as="style"
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;510;590;700&display=swap" />
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;510;590;700&display=swap"
  media="print" onload="this.media='all'" />
```
Load Padauk + Noto Sans Myanmar only on Myanmar pages:
```astro
{lang === 'my' && (
  <link rel="stylesheet"
    href="https://fonts.googleapis.com/css2?family=Padauk:wght@400;700&family=Noto+Sans+Myanmar:wght@400;500;700&display=swap" />
)}
```

### H2. Dynamic import Fuse.js — 30 min
**Removes 25 kB from every page's JS critical path**

In `Base.astro` search script, replace direct Fuse import with:
```javascript
trigger.addEventListener('click', async () => {
  const { default: Fuse } = await import('fuse.js')
  // rest of initSearch
})
```

### H3. Switch to output: 'hybrid', prerender static pages — 2–3 hrs
`astro.config.mjs` → `output: 'hybrid'`. Mark article, digest, and all static pages `prerender = true`. Reserve SSR only for `/api/*`, Keystatic routes, live Observatory endpoints. Eliminates 50–200ms cold-start TTFB on every article load.

### H4. Fix Organization schema — 45 min
`src/components/SchemaOrg.astro`:
- `@type: NewsMediaOrganization`
- `@id: "https://www.internetinmyanmar.com/#organization"`
- Add `logo: { "@type": "ImageObject", "url": "https://www.internetinmyanmar.com/og-default.png" }`
- Remove `sameAs: ["https://www.internetinmyanmar.com"]` (self-referential)

### H5. Fix Person schema for Anna — 20 min
`src/pages/about/anna.astro`:
- `name: 'Anna Faure Revol'`
- `@id: "https://www.internetinmyanmar.com/about/anna/#person"`
- `worksFor` → `NewsMediaOrganization` with `@id`

`src/layouts/Article.astro` byline: render full name, populate bio paragraph.

### H6. Replace SVG OG fallback with PNG — 30 min
Generate `/public/og-default.png` at 1200×630. Update `Base.astro` OG image default reference.

### H7. Add hreflang to `<head>` — 1 hr
`Base.astro`: loop locales, emit `<link rel="alternate" hreflang>` for en/fr/es/it + `x-default` using existing `getLocalePath()`.

### H8. Fix llms.txt — 20 min
`public/llms.txt`:
- `Editor: Anna` → `Editor: Anna Faure Revol`
- Convert relative URLs to absolute (`/observatory/bgp` → `https://www.internetinmyanmar.com/observatory/bgp`)
- Add `License: https://creativecommons.org/licenses/by/4.0/`

### H9. Add featured image dimensions + fetchpriority — 15 min
`src/layouts/Article.astro` featured `<img>`:
```astro
width="1200" height="675" fetchpriority="high"
```

---

## MEDIUM — Within 1 month

### M1. Add BreadcrumbList schema to articles — 1 hr
`Article.astro`: generate JSON-LD `BreadcrumbList` from existing `primaryCategory` + `categoryHref` + `slug` variables. Already rendered visually — just needs schema.

### M2. Add WebSite schema to Base.astro — 30 min
Add `WebSite` JSON-LD with `@id` and publisher reference. Enables Sitelinks Searchbox eligibility.

### M3. Create public/_headers — 1 hr
```
/*
  X-Frame-Options: SAMEORIGIN
  Referrer-Policy: strict-origin-when-cross-origin
  X-Content-Type-Options: nosniff
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

### M4. Rewrite vpn-myanmar.mdx — 2–3 hrs editorial
Full rewrite: post-coup VPN landscape, Tor/Psiphon/Lantern focus, safety warnings for activists under junta surveillance. Remove all 2018 affiliate recommendations.

### M5. Fix seoTitle truncations — 30 min
```bash
grep 'seoTitle.*…' src/content/articles/*.mdx
```
Rewrite to proper ≤60 char titles without ellipsis character.

### M6. Fix lang field on remaining Burmese articles — 10 min
Set `lang: "my"` on `bypass-country-google-play-store-mm.mdx` and `cookie-tv-app-myanmar.mdx`.

### M7. Add `updatedAt` to stale evergreen articles — ongoing editorial
Priority: `ixp-internet-exchange-myanmar`, `internet-myanmar-expensive`, `myanmar-internet-censorship`. Set when Anna reviews and updates.

### M8. Add question-based headings to top articles — editorial
Restructure 5–10 key articles with question-headed H2/H3 + self-contained 134–167 word answer blocks. Enables Google AI Overviews and Featured Snippets extraction.
Priority articles: `myanmar-digital-repression-2026`, `myanmar-internet-censorship`, and the vpn rewrite.

### M9. Deduplicate metaDescriptions across language pairs — 30 min
Write unique metaDescriptions for: `fiber-broadband-ftth-myanmar` / `fiber-broadband-ftth-myanmar-my` and `spotify-myanmar` / `how-to-use-spotify-myanmar-my`.

### M10. Add `<lastmod>` to sitemap — 1 hr
After C2 is done, configure `@astrojs/sitemap` `serialize` option to inject `lastmod` from `updatedAt ?? publishedAt` frontmatter values.

---

## LOW — Backlog

- **L1. IndexNow** — Add `/[key].txt` to `public/`, call IndexNow API in `agents/publisher.py` on new article publish
- **L2. AI crawler directives in robots.txt** — Explicit Allow for GPTBot/PerplexityBot/ClaudeBot; consider Disallow for training-only bots (CCBot, anthropic-ai)
- **L3. Self-host Inter** — Eliminate Google Fonts third-party DNS lookup for repeat visitors
- **L4. Anna's LinkedIn + Wikidata** — Add to Person schema `sameAs` once LinkedIn URL confirmed; create Wikidata Q-identifier
- **L5. Schema keywords** — Inject article `tags` as `keywords` in NewsArticle schema (after cleaning keyword-stuffed tags)
- **L6. RSS `<link>` in `<head>`** — Add `<link rel="alternate" type="application/rss+xml" href="/rss.xml">` to `Base.astro`

---

## Sprint Order

| Today (30 min) | This week (8 hrs dev) | Next week (6 hrs dev) | Month |
|---|---|---|---|
| C1 draft 7 articles | C2 sitemap/prerender | H4 Org schema | M1–M10 rolling |
| C4 HSTS | C3 NewsArticle schema | H5 Person schema | |
| C5 affiliate link | H1 Google Fonts | H7 hreflang | |
| | H2 Fuse.js | H8 llms.txt | |
| | H6 OG PNG | H9 img dimensions | |
| | H3 hybrid prerender | M3 _headers | |
