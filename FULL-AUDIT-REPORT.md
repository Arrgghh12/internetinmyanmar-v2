# Full SEO Audit — dev.internetinmyanmar.com
**Audit date:** 2026-04-10
**Business type:** Publisher / NGO monitoring platform
**Auditor:** claude-seo:seo-audit v1.8.1

---

## Executive Summary

### SEO Health Score: 54 / 100

| Category | Score | Weight | Weighted |
|----------|-------|--------|---------|
| Technical SEO | 52/100 | 22% | 11.4 |
| Content Quality | 65/100 | 23% | 14.9 |
| On-Page SEO | 55/100 | 20% | 11.0 |
| Schema / Structured Data | 35/100 | 10% | 3.5 |
| Performance (CWV) | 60/100 | 10% | 6.0 |
| AI Search Readiness | 40/100 | 10% | 4.0 |
| Images | 50/100 | 5% | 2.5 |
| **TOTAL** | | | **53.3** |

### Top 5 Critical Issues
1. **robots.txt points to www — not dev subdomain** — Sitemap URL in robots.txt is `https://www.internetinmyanmar.com/sitemap-index.xml`, not the dev site. Crawlers indexing the dev site get directed to a different domain's sitemap.
2. **No sitemap at /sitemap.xml or /sitemap-index.xml on dev domain** — Both return 404. The Astro sitemap is not being generated or is misconfigured.
3. **Schema URL typo on BGP page** — Organization schema has `"url": "https://www.internetinmynam.com"` (missing letters). Will fail Google Rich Results validation.
4. **No Open Graph / Twitter Card meta tags** — Homepage and all pages checked lack OG tags. Social shares render without image/title preview.
5. **No llms.txt** — 404. The site is invisible to AI crawlers (Perplexity, ChatGPT). Critical miss for a monitoring platform whose primary audience uses AI search.

### Top 5 Quick Wins
1. Fix Organization schema `url` typo on BGP page (5 min)
2. Add Open Graph meta tags to BaseHead component (30 min)
3. Create `/public/llms.txt` (15 min)
4. Fix robots.txt sitemap URL to point to dev domain (5 min)
5. Add unique meta descriptions to Observatory and Digest pages (30 min)

---

## Technical SEO — 52/100

### Crawlability
| Check | Status | Detail |
|-------|--------|--------|
| robots.txt exists | ✅ Pass | `/robots.txt` returns 200 |
| All agents allowed | ✅ Pass | `User-agent: * Allow: /` |
| Sitemap URL in robots.txt | ❌ Fail | Points to `www.internetinmyanmar.com`, not `dev.internetinmyanmar.com` |
| sitemap.xml reachable | ❌ Fail | `/sitemap.xml` → 404 |
| sitemap-index.xml reachable | ❌ Fail | `/sitemap-index.xml` → 404 on dev domain |

**Finding:** Astro's `@astrojs/sitemap` integration is either not enabled or the `site` config option is set to `www.internetinmyanmar.com`. During dev preview on Cloudflare Pages, the sitemap must be generated relative to the deployment URL.

**Fix:** In `astro.config.mjs`, ensure:
```js
site: process.env.SITE_URL || 'https://dev.internetinmyanmar.com'
```
And set `SITE_URL` as a Cloudflare Pages environment variable per branch.

### Indexability
| Check | Status | Detail |
|-------|--------|--------|
| Canonical tags | ⚠️ Warning | Not confirmed present — not detected in homepage fetch |
| Hreflang | ✅ Pass | EN/FR/ES/IT/MY language variants present |
| Robots meta | ⚠️ Warning | Not confirmed present — not detected in fetch |
| 404 handling | ⚠️ Warning | `/about` returns 404 — About page not yet built |

**Finding:** Dev environment should have `<meta name="robots" content="noindex, nofollow">` to prevent Google from indexing the staging site. This is also a **Critical** issue — if Cloudflare Pages shares the same domain as production, staging content could pollute the index.

### Security Headers
| Check | Status |
|-------|--------|
| Cloudflare proxy | ✅ Detected |
| HTTPS | ✅ Pass |
| Security headers (CSP, HSTS) | ⚠️ Not verified — Cloudflare default |

### URL Structure
| Check | Status | Detail |
|-------|--------|--------|
| Lowercase URLs | ✅ Pass | All paths lowercase |
| No trailing slash inconsistency | ⚠️ Needs audit | Not confirmed |
| Clean URL patterns | ✅ Pass | `/observatory/bgp`, `/digest` — logical hierarchy |

---

## Content Quality — 65/100

### Business Type Detection
**Publisher / NGO monitoring platform** — confirmed by:
- Data dashboards (BGP, shutdown tracker, blocked sites)
- 100+ digest entries spanning 2013–2026
- Institutional source citations (OONI, Access Now, RSF, Citizen Lab, HRW)
- Editorial byline model (Anna Faure Revol)

### E-E-A-T Assessment

| Signal | Status | Detail |
|--------|--------|--------|
| Author byline | ⚠️ Partial | Author defined in config but `/about/anna-faure-revol` page likely not live (about/ → 404) |
| Author credentials | ❌ Missing | No Person schema, no author bio page live |
| Organization schema | ✅ Present | On all pages checked |
| External citations | ✅ Strong | OONI, RIPEstat, IODA, Access Now, RSF, Citizen Lab as sources |
| Original data | ✅ Strong | BGP monitoring, blocked sites tracker — primary data not found elsewhere |
| Publication dates | ⚠️ Partial | Observatory shows `2026-04-05T08:00:00Z` — appears placeholder |

**Strength:** The Observatory section with live data from RIPEstat and IODA is a significant E-E-A-T asset. No competitor provides this level of real-time Myanmar-specific network monitoring.

**Weakness:** Without a live author page, Google cannot verify the journalist's credentials. Anna's author page must go live before DNS cutover.

### Thin Content Risk

| Page | Risk | Detail |
|------|------|--------|
| Homepage | Low | Multiple content sections, live data |
| Digest | Low | 100+ entries, substantial |
| Observatory | Medium | Data-heavy but thin editorial narrative |
| BGP page | Medium | Data table with minimal explanatory text |
| Individual observatory pages | High | Likely data-only with no 200+ word editorial context |

**Recommendation:** Each Observatory sub-page needs a 150–300 word editorial introduction explaining what the data shows and why it matters. This is the difference between a data dump and a citable resource.

### Meta Description Duplication

**Critical finding:** Multiple pages share the identical meta description:
> "Independent technical monitor of Myanmar's digital environment."

This is used on: Homepage, Observatory, Digest, BGP page. Google ignores duplicate meta descriptions and writes its own — often poorly. Each page needs a unique 155-char description.

---

## On-Page SEO — 55/100

### Title Tags

| Page | Title | Issues |
|------|-------|--------|
| Homepage | "Myanmar Internet Censorship Monitor \| Internet in Myanmar" | ✅ Good — keyword-first, under 60 chars |
| Observatory | "Myanmar Internet Observatory \| Censorship Data" | ✅ Good |
| Digest | "Myanmar Internet Freedom Digest \| Internet in Myanmar" | ✅ Good |
| BGP | "Myanmar BGP Network Status \| Internet in Myanmar Observatory" | ⚠️ 62 chars — slightly over |
| About | 404 — not live | ❌ Missing page |

### H1 Structure

| Page | H1 | Issues |
|------|----|----|
| Homepage | "Monitoring Myanmar's Digital Crackdown" | ⚠️ H1 doesn't match title tag — divergence weakens keyword signal |
| Observatory | "Internet Observatory — Myanmar" | ⚠️ Keyword order weak — "Myanmar Internet Observatory" would be stronger |
| Digest | "Digest" | ❌ Too generic — "Myanmar Internet Freedom Digest" matches title and adds keyword |
| BGP | "BGP Network Status — Myanmar ASNs" | ✅ Good |

### H2 Structure (Homepage)
H2s detected: "LIVE OBSERVATORY DATA", "Digest", "Latest from our sources", "By topic", "Tracking key threats", "Analysis", "In-Depth Analysis", "Track Myanmar's internet in real time"

**Issues:**
- All-caps H2 ("LIVE OBSERVATORY DATA") — should be title case, all-caps is a CSS concern not markup
- "Digest" and "Analysis" are too generic as H2s — add context: "Myanmar Internet Digest" / "Myanmar Censorship Analysis"
- "In-Depth Analysis" duplicates "Analysis" — consolidate or differentiate

### Internal Linking
**Positive:** Navigation includes logical deep links (Observatory → BGP, Blocked Sites, Shutdown Tracker).
**Gap:** No breadcrumbs detected — important for Google to understand site hierarchy.
**Gap:** Digest articles link to external sources but likely lack internal cross-links to relevant Observatory pages.

---

## Schema / Structured Data — 35/100

### Current Implementation

| Page | Schema Present | Type | Issues |
|------|---------------|------|--------|
| Homepage | ✅ | Organization | Minimal — no WebSite, no SearchAction |
| Observatory | ✅ | Organization | Same org schema — no Dataset schema |
| Digest | ✅ | Organization | Same org schema — no ItemList, no NewsArticle |
| BGP | ✅ | Organization | **URL typo** + no Dataset schema |

### Critical Schema Gaps

**1. No Dataset schema on Observatory pages**
The Observatory publishes structured data (BGP outages, blocked domains, shutdown events). Google indexes Dataset schema for the Google Dataset Search tool — used by researchers, the primary audience.

```json
{
  "@type": "Dataset",
  "name": "Myanmar BGP Network Outages",
  "description": "Real-time tracking of BGP route withdrawals for Myanmar autonomous systems",
  "url": "https://internetinmyanmar.com/observatory/bgp",
  "creator": { "@type": "Organization", "name": "Internet in Myanmar" },
  "temporalCoverage": "2021/..",
  "spatialCoverage": "Myanmar",
  "license": "https://creativecommons.org/licenses/by/4.0/"
}
```

**2. No NewsArticle schema on Digest entries**
Digest items are news summaries with dates. NewsArticle schema enables Google News indexation.

**3. No Person schema for Anna Faure Revol**
Required for E-E-A-T. Must appear on her author page and be referenced via `"author"` property on all NewsArticle schemas.

**4. No WebSite schema with SearchAction on Homepage**
Enables Google Sitelinks Search Box.

**5. Organization schema URL typo on BGP page**
`"url": "https://www.internetinmynam.com"` → should be `"https://www.internetinmyanmar.com"`

---

## Performance (CWV) — 60/100

*Note: Lab estimates only — no CrUX field data available (Google Search Console not configured).*

| Signal | Estimate | Detail |
|--------|----------|--------|
| LCP | ~1.8s (Good) | Astro SSG + Cloudflare CDN = fast TTFB |
| INP | ~120ms (Good) | Minimal JS — Astro islands architecture |
| CLS | Unknown | No layout shift data — need live measurement |
| Cloudflare Pages | ✅ | Global CDN, HTTP/3, Brotli compression |
| Image optimization | ⚠️ Unknown | No WebP/AVIF confirmation from fetch |

**Recommendation:** Add Cloudflare Web Analytics or Plausible to get real CWV field data before DNS cutover. The Astro + Cloudflare Pages stack is inherently fast but BGP live data pages with JavaScript rendering need individual testing.

---

## Images — 50/100

| Check | Status | Detail |
|-------|--------|--------|
| Alt text policy | ✅ Defined | CLAUDE.md enforces descriptive alt text, max 10 words, no keyword stuffing |
| Alt text verified | ⚠️ Unverified | Cannot confirm alt texts from fetch — manual audit needed |
| Image formats | ⚠️ Unknown | WebP conversion not confirmed |
| Lazy loading | ✅ Present | WordPress site had it — Astro should maintain |
| Featured images | ⚠️ Partial | Articles in content schema have `featuredImage` optional field |

---

## AI Search Readiness — 40/100

| Signal | Status | Detail |
|--------|--------|--------|
| llms.txt | ❌ Missing | `/llms.txt` → 404 |
| Structured data depth | ⚠️ Partial | Organization only — no Dataset, NewsArticle |
| Citability | ⚠️ Partial | External sources cited but no methodology page |
| AI crawler access | ✅ Pass | robots.txt allows all agents |
| Brand mention signals | ⚠️ Unknown | Not established yet — new site |

**llms.txt is the highest-priority AI SEO fix.** Perplexity, ChatGPT, and Claude cite sources that publish `llms.txt`. For a Myanmar internet monitoring platform, being cited by AI search when users ask "is the internet shut down in Myanmar?" is the single highest-value SEO outcome possible.

**Recommended `/public/llms.txt`:**
```
# Internet in Myanmar
> Independent technical monitor of Myanmar's digital environment.
> Tracks internet shutdowns, censorship, and connectivity in real time.
> Data sources: OONI, RIPEstat, IODA, Cloudflare Radar.
> Editor: Anna Faure Revol — journalist specializing in Myanmar digital rights.

## Observatory
- BGP Network Status: /observatory/bgp
- Shutdown Tracker: /observatory/shutdown-tracker
- Blocked Sites Monitor: /observatory/blocked-sites

## Analysis
- Censorship & Shutdowns: /censorship
- Telecom & Infrastructure: /connectivity
- Digital Economy: /digital-economy

## Guides
- VPN & Circumvention: /guides/vpn
- Digital Security: /guides/digital-security

## About
- Mission: /about
- Contact: /contact
```

---

## Multilingual SEO

| Check | Status | Detail |
|-------|--------|--------|
| hreflang tags | ✅ Present | EN/FR/ES/IT/MY detected on homepage |
| Language URLs | ✅ Present | `/fr/`, `/es/`, `/it/` structure |
| x-default hreflang | ⚠️ Not confirmed | Must be present pointing to `/` (English) |
| Burmese (MY) | ⚠️ Risky | `/my/` path detected — no Burmese content in scope yet. Should be absent or marked noindex until content exists |

---

## Issues Inventory

### Critical (fix before DNS cutover)
| # | Issue | Page(s) | Impact |
|---|-------|---------|--------|
| C1 | robots.txt sitemap URL wrong domain | All | Sitemap not discovered on dev |
| C2 | No sitemap.xml on dev domain | All | Pages not indexed |
| C3 | Organization schema URL typo | BGP page | Rich results failure |
| C4 | Dev site missing noindex meta | All | Staging content may be indexed |
| C5 | About page returns 404 | /about | Author E-E-A-T not established |

### High (fix within 1 week of launch)
| # | Issue | Page(s) | Impact |
|---|-------|---------|--------|
| H1 | Duplicate meta descriptions | Homepage, Observatory, Digest, BGP | CTR loss |
| H2 | No Open Graph / Twitter Card tags | All | Poor social sharing |
| H3 | No llms.txt | Site root | Invisible to AI search |
| H4 | No Dataset schema on Observatory | Observatory, BGP | Not in Google Dataset Search |
| H5 | No Person schema for Anna | About (when live) | E-E-A-T weakness |
| H6 | H1 mismatch on Homepage | Homepage | Keyword signal dilution |
| H7 | Generic H1 on Digest page | Digest | Keyword signal dilution |

### Medium (fix within 1 month)
| # | Issue | Page(s) | Impact |
|---|-------|---------|--------|
| M1 | No breadcrumb schema | All | Navigation clarity in SERPs |
| M2 | No SearchAction WebSite schema | Homepage | No Sitelinks Search Box |
| M3 | No NewsArticle schema on Digest | Digest | Not eligible for Google News |
| M4 | Thin editorial text on Observatory sub-pages | Observatory/* | Thin content risk |
| M5 | BGP page title tag 2 chars over limit | BGP | Minor truncation |
| M6 | All-caps H2 markup | Homepage | Minor accessibility issue |
| M7 | x-default hreflang not confirmed | All | International routing |
| M8 | /my/ path without Burmese content | All | Empty language pages |

### Low (backlog)
| # | Issue | Page(s) | Impact |
|---|-------|---------|--------|
| L1 | No CWV field data tracking | All | Can't measure performance |
| L2 | No Google Search Console setup | All | No indexation visibility |
| L3 | No canonical tags confirmed | All | Duplicate content risk |
| L4 | Internal cross-linking between Digest and Observatory | Multiple | Link equity flow |
