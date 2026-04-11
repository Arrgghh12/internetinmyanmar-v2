# SEO Action Plan — dev.internetinmyanmar.com
**Generated:** 2026-04-10
**Based on:** FULL-AUDIT-REPORT.md

---

## CRITICAL — Fix before DNS cutover

### C1 · Fix robots.txt sitemap URL
**File:** `public/robots.txt`
**Effort:** 5 min

```
User-agent: *
Allow: /
Sitemap: https://www.internetinmyanmar.com/sitemap-index.xml
```

→ The sitemap URL must match the deployment domain. Use Astro's `site` variable:

```
# public/robots.txt — replace hardcoded URL with Astro-generated sitemap
User-agent: *
Allow: /
Sitemap: https://www.internetinmyanmar.com/sitemap-index.xml
```

**For dev branch**, add a `_headers` rule or Cloudflare Pages rule to override the sitemap URL, OR generate robots.txt dynamically in `src/pages/robots.txt.ts`:

```ts
// src/pages/robots.txt.ts
import type { APIRoute } from 'astro';
export const GET: APIRoute = ({ site }) => {
  return new Response(
    `User-agent: *\nAllow: /\nSitemap: ${site}sitemap-index.xml\n`
  );
};
```

---

### C2 · Fix sitemap generation
**File:** `astro.config.mjs`
**Effort:** 10 min

Ensure `@astrojs/sitemap` is installed and `site` is set:

```js
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: process.env.SITE_URL ?? 'https://www.internetinmyanmar.com',
  integrations: [sitemap()],
});
```

Set `SITE_URL=https://dev.internetinmyanmar.com` in Cloudflare Pages → dev branch environment variables.

---

### C3 · Fix Organization schema URL typo on BGP page
**File:** Wherever Organization schema is defined (likely `src/layouts/Base.astro` or a shared schema component)
**Effort:** 5 min

Find and fix:
```diff
- "url": "https://www.internetinmynam.com"
+ "url": "https://www.internetinmyanmar.com"
```

Grep for it: `grep -r "internetinmynam.com" src/`

---

### C4 · Add noindex to dev/staging deployment
**File:** `src/layouts/BaseHead.astro` (or equivalent)
**Effort:** 10 min

```astro
---
const isProduction = import.meta.env.SITE_URL?.includes('internetinmyanmar.com')
  && !import.meta.env.SITE_URL?.includes('dev.');
---
{!isProduction && <meta name="robots" content="noindex, nofollow" />}
```

Or use a Cloudflare Pages `_headers` file for the dev deployment:
```
# public/_headers  (apply only when deploying to dev branch)
/*
  X-Robots-Tag: noindex
```

---

### C5 · Build the About / Anna page
**File:** `src/pages/about/index.astro` + `src/pages/about/anna-faure-revol.astro`
**Effort:** 2–4 hours

The About page returns 404. This is the E-E-A-T anchor for the entire site.
Minimum required before launch:
- `/about` — mission page with Organization schema
- `/about/anna-faure-revol` — author page with Person schema (see H5 below)

---

## HIGH — Fix within 1 week of launch

### H1 · Write unique meta descriptions for every page
**File:** Each page's frontmatter or layout props
**Effort:** 1 hour

Current: all pages share `"Independent technical monitor of Myanmar's digital environment."`

| Page | Suggested meta description (≤155 chars) |
|------|----------------------------------------|
| Homepage | Track Myanmar's internet shutdowns, censorship, and connectivity in real time. Independent data from OONI, RIPEstat, and Cloudflare Radar. |
| Observatory | Live dashboard: Myanmar internet shutdowns, BGP outages, and blocked sites. Updated every 12 hours from OONI, RIPEstat, and IODA. |
| Digest | Curated daily digest of Myanmar internet freedom news from RSF, Access Now, Citizen Lab, OONI, and international press. |
| BGP page | Real-time BGP route monitoring for 150+ Myanmar autonomous systems. Tracks network outages, ISP disruptions, and military-ordered shutdowns. |
| Blocked Sites | Database of 847+ websites blocked by Myanmar ISPs, with confirmation dates and blocking methods. |
| Shutdown Tracker | Timeline of internet shutdowns in Myanmar since 2021: duration, affected regions, and documented human rights impact. |

---

### H2 · Add Open Graph and Twitter Card meta tags
**File:** `src/layouts/BaseHead.astro`
**Effort:** 30 min

```astro
---
const { title, description, image, url } = Astro.props;
const ogImage = image ?? '/images/og-default.png';
---

<!-- Open Graph -->
<meta property="og:type" content="website" />
<meta property="og:url" content={url ?? Astro.url} />
<meta property="og:title" content={title} />
<meta property="og:description" content={description} />
<meta property="og:image" content={new URL(ogImage, Astro.site)} />
<meta property="og:site_name" content="Internet in Myanmar" />

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content={title} />
<meta name="twitter:description" content={description} />
<meta name="twitter:image" content={new URL(ogImage, Astro.site)} />
```

Create a default OG image at `public/images/og-default.png` (1200×630px, dark background, logo, tagline).

---

### H3 · Create /public/llms.txt
**File:** `public/llms.txt`
**Effort:** 15 min

```
# Internet in Myanmar
> Independent technical monitor of Myanmar's digital environment.
> Tracks internet shutdowns, censorship, and connectivity in real time.
> Data sources: OONI, RIPEstat, IODA, Cloudflare Radar, NetBlocks.
> Editor: Anna Faure Revol — journalist specializing in Myanmar digital rights.

## Observatory (live data)
- BGP Network Status — 150+ Myanmar ASNs: /observatory/bgp
- Shutdown Tracker — timeline since 2021: /observatory/shutdown-tracker
- Blocked Sites Monitor — 847+ confirmed blocked domains: /observatory/blocked-sites

## Analysis
- Censorship & Shutdowns: /censorship
- Telecom & Infrastructure: /connectivity
- Digital Economy: /digital-economy

## Guides
- VPN & Circumvention for Myanmar: /guides/vpn
- Digital Security: /guides/digital-security
- SIM Cards & Connectivity: /guides/connectivity

## About
- Mission & methodology: /about
- Anna Faure Revol (editor): /about/anna-faure-revol
- Contact: /contact

## Data methodology
- BGP data sourced from RIPEstat (RIPE NCC) and IODA (Georgia Tech)
- Blocking confirmations via OONI Explorer measurement data
- Shutdown events cross-referenced with NetBlocks and Cloudflare Radar
```

---

### H4 · Add Dataset schema to Observatory pages
**File:** `src/pages/observatory/bgp.astro`, `src/pages/observatory/shutdown-tracker.astro`, `src/pages/observatory/blocked-sites.astro`
**Effort:** 1 hour

```astro
---
const datasetSchema = {
  "@context": "https://schema.org",
  "@type": "Dataset",
  "name": "Myanmar BGP Network Outages",
  "description": "Real-time tracking of BGP route withdrawals for Myanmar autonomous systems (ASNs), sourced from RIPEstat and IODA.",
  "url": "https://www.internetinmyanmar.com/observatory/bgp",
  "creator": {
    "@type": "Organization",
    "name": "Internet in Myanmar",
    "url": "https://www.internetinmyanmar.com"
  },
  "publisher": {
    "@type": "Organization",
    "name": "Internet in Myanmar"
  },
  "temporalCoverage": "2021/..",
  "spatialCoverage": {
    "@type": "Place",
    "name": "Myanmar"
  },
  "license": "https://creativecommons.org/licenses/by/4.0/",
  "isAccessibleForFree": true,
  "keywords": ["Myanmar", "internet shutdown", "BGP", "censorship", "ASN"]
}
---
<script type="application/ld+json" set:html={JSON.stringify(datasetSchema)} />
```

---

### H5 · Add Person schema for Anna Faure Revol
**File:** `src/pages/about/anna-faure-revol.astro`
**Effort:** 30 min

```json
{
  "@context": "https://schema.org",
  "@type": "Person",
  "name": "Anna Faure Revol",
  "jobTitle": "Editor-in-Chief",
  "description": "Journalist specializing in Myanmar's media landscape, digital rights, and internet freedom.",
  "url": "https://www.internetinmyanmar.com/about/anna-faure-revol",
  "worksFor": {
    "@type": "Organization",
    "name": "Internet in Myanmar",
    "url": "https://www.internetinmyanmar.com"
  },
  "knowsAbout": ["Myanmar", "internet censorship", "digital rights", "media freedom", "Southeast Asia"]
}
```

Reference this Person in every NewsArticle schema:
```json
"author": {
  "@type": "Person",
  "name": "Anna Faure Revol",
  "url": "https://www.internetinmyanmar.com/about/anna-faure-revol"
}
```

---

### H6 · Fix H1 mismatch on Homepage
**File:** `src/pages/index.astro`
**Effort:** 5 min

Current H1: `"Monitoring Myanmar's Digital Crackdown"`
Title tag: `"Myanmar Internet Censorship Monitor | Internet in Myanmar"`

H1 and title tag should share primary keywords. Options:
- H1: `"Myanmar Internet Censorship Monitor"` (matches title exactly)
- H1: `"Myanmar's Internet Censorship — Live Monitor"` (more editorial, still keyword-aligned)

---

### H7 · Fix generic H1 on Digest page
**File:** `src/pages/digest/index.astro` (or equivalent)
**Effort:** 5 min

```diff
- <h1>Digest</h1>
+ <h1>Myanmar Internet Freedom Digest</h1>
```

---

## MEDIUM — Fix within 1 month

### M1 · Add BreadcrumbList schema
**File:** `src/layouts/Base.astro` or a `Breadcrumb.astro` component
**Effort:** 1 hour

Add breadcrumb nav + schema to all pages below homepage:
```json
{
  "@type": "BreadcrumbList",
  "itemListElement": [
    { "@type": "ListItem", "position": 1, "name": "Home", "item": "https://www.internetinmyanmar.com" },
    { "@type": "ListItem", "position": 2, "name": "Observatory", "item": "https://www.internetinmyanmar.com/observatory" },
    { "@type": "ListItem", "position": 3, "name": "BGP Network Status", "item": "https://www.internetinmyanmar.com/observatory/bgp" }
  ]
}
```

---

### M2 · Add WebSite schema with SearchAction
**File:** `src/layouts/BaseHead.astro` — homepage only
**Effort:** 15 min

```json
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "Internet in Myanmar",
  "url": "https://www.internetinmyanmar.com",
  "potentialAction": {
    "@type": "SearchAction",
    "target": {
      "@type": "EntryPoint",
      "urlTemplate": "https://www.internetinmyanmar.com/search?q={search_term_string}"
    },
    "query-input": "required name=search_term_string"
  }
}
```

Note: Only add if search functionality exists or is planned.

---

### M3 · Add NewsArticle schema to Digest entries
**File:** Digest article component
**Effort:** 2 hours

Each digest item should render with NewsArticle schema including `datePublished`, `author`, `publisher`, `headline`, `url`, `description`.

---

### M4 · Add editorial introductions to Observatory sub-pages
**Files:** `src/pages/observatory/bgp.astro`, `shutdown-tracker.astro`, `blocked-sites.astro`
**Effort:** 3 hours (writing)

Each page needs 150–250 words of editorial context:
- **BGP page:** Explain what BGP is, why route withdrawals indicate shutdowns, what Myanmar's ASN landscape looks like
- **Shutdown Tracker:** Brief methodology note — what counts as a shutdown, data sources, confidence levels
- **Blocked Sites:** Explain OONI measurement methodology, what "confirmed blocked" means

This text is also what AI search engines and LLMs quote when users ask about Myanmar internet shutdowns.

---

### M5 · Trim BGP page title tag
**File:** `src/pages/observatory/bgp.astro`
**Effort:** 2 min

```diff
- "Myanmar BGP Network Status | Internet in Myanmar Observatory"  (62 chars)
+ "Myanmar BGP Network Status | Internet in Myanmar"              (49 chars)
```

---

### M6 · Fix all-caps H2 markup
**File:** Homepage component
**Effort:** 5 min

```diff
- <h2>LIVE OBSERVATORY DATA</h2>
+ <h2>Live Observatory Data</h2>
```

Use CSS `text-transform: uppercase` if the visual style requires all-caps.

---

### M7 · Verify x-default hreflang
**File:** `src/layouts/BaseHead.astro`
**Effort:** 10 min

Ensure this tag is present on all pages alongside the language variants:
```html
<link rel="alternate" hreflang="x-default" href="https://www.internetinmyanmar.com/" />
```

---

### M8 · Handle /my/ (Burmese) path
**File:** Astro i18n config
**Effort:** 30 min

Until Burmese content is published, either:
- Remove `/my/` from hreflang tags entirely
- Add `<meta name="robots" content="noindex">` to all `/my/` pages

Having language variants that resolve to empty pages is an indexation quality signal.

---

## LOW — Backlog

### L1 · Set up Cloudflare Web Analytics or Plausible
Needed to get real CWV field data before DNS cutover. Plausible is privacy-compliant and has no consent banner requirement — right choice for this audience.

### L2 · Set up Google Search Console
Connect GSC to the production domain before DNS cutover. Submit sitemap on day 1. Monitor index coverage weekly for the first month.

### L3 · Verify canonical tags on all pages
Confirm `<link rel="canonical">` is present in BaseHead. Check for self-referencing canonicals on all pages and correct cross-language canonicals (each language variant should canonicalize to itself, not to English).

### L4 · Build internal cross-links: Digest ↔ Observatory
When Digest articles mention a shutdown event, link to the relevant Observatory tracker. When Observatory pages mention sources, link to related Digest entries. Target: 3–5 internal links per page.

---

## Summary Checklist

```
CRITICAL (before DNS cutover):
[ ] C1 — robots.txt sitemap URL dynamic
[ ] C2 — sitemap.xml generating on dev domain
[ ] C3 — Organization schema URL typo fixed
[ ] C4 — noindex on dev/staging deployment
[ ] C5 — About page live with author content

HIGH (week 1 post-launch):
[ ] H1 — Unique meta descriptions on all pages
[ ] H2 — Open Graph + Twitter Card tags in BaseHead
[ ] H3 — /public/llms.txt created
[ ] H4 — Dataset schema on Observatory pages
[ ] H5 — Person schema for Anna on About page
[ ] H6 — H1 aligned with title tag on Homepage
[ ] H7 — Generic "Digest" H1 expanded

MEDIUM (month 1):
[ ] M1 — BreadcrumbList schema
[ ] M2 — WebSite + SearchAction schema
[ ] M3 — NewsArticle schema on Digest
[ ] M4 — Editorial text on Observatory sub-pages
[ ] M5 — BGP title tag trimmed
[ ] M6 — All-caps H2 fixed
[ ] M7 — x-default hreflang verified
[ ] M8 — /my/ path handled

LOW (backlog):
[ ] L1 — Analytics setup
[ ] L2 — Google Search Console
[ ] L3 — Canonical tags verified
[ ] L4 — Internal cross-linking Digest ↔ Observatory
```
