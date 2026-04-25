# CLAUDE.md — Internet in Myanmar v2
# Project context — read entirely before any action
# Last updated: 2026-04-25

---

## TOKEN EFFICIENCY — READ THIS FIRST

```
DO:
→ Read only files relevant to the current task
→ Use grep/find to locate files instead of reading directories
→ Write complete files in one shot
→ Chain commands: cmd1 && cmd2 && cmd3

DO NOT:
→ Summarize what you are about to do — just do it
→ Explain what you just did — output speaks for itself
→ Ask questions if the answer is in CLAUDE.md
→ Re-read files already read in this session
→ Read config files (package.json, astro.config) on every session start
```

Python agents: respond with exact output only. No preamble. No markdown fences unless output IS code.
Model selection and token limits live in `agents/config.yaml`.

---

## PROJECT

Rebuilding internetinmyanmar.com from WordPress to Astro.

**Mission:** Independent technical monitor of Myanmar's digital environment.
Tracking censorship, internet shutdowns, and connectivity for journalists,
researchers, and international organizations.

**Current site:** https://www.internetinmyanmar.com (WordPress — stays live during dev)
**New site:** internetinmyanmar.com → Cloudflare Pages (replaces WP when ready)

---

## TEAM

### Editor-in-Chief — Anna
- **All published articles are bylined: Anna** (never "Anna Faure Revol" — surname not used on site)
- Speciality: Myanmar, Southeast Asia, digital rights, media freedom
- Languages: French, English, Spanish, Italian
- Author bio: "Anna is a journalist specializing in Myanmar's media landscape, digital rights, and internet freedom. She has closely followed the military junta's systematic censorship of online information since the 2021 coup."
- Tone: precise, analytical, never sensationalist. Credible to both OONI/Citizen Lab and RSF/Freedom House audiences.
- Anna validates all briefs and publishes all articles.

### Technical Director (stays anonymous)
- Manages infrastructure, Claude Code pipeline, VPS agents — not public on site.

### Former WP authors — do not carry over
- "Myanmar Geek", "Herbert Kanale", "Miss PR" → all retired/discarded

---

## MULTILINGUAL STRATEGY

```
English  → primary, all articles first
French   → key investigative pieces — targets RSF, francophone donors
Spanish  → selected pieces — targets FLIP, Spanish-language press freedom orgs
Italian  → occasional — European institutional outreach
```

Astro i18n routing. Agents produce draft translations → Anna reviews. Anna decides per article.

---

## INFRASTRUCTURE

```
Dev machine:  Windows 11 + WSL2 Ubuntu · repo at ~/dev/iimv2 · dev server localhost:4321
GitHub:       Arrgghh12/internetinmyanmar-v2
Branches:     main → production · dev → dev.internetinmyanmar.com · draft/* → per-article PRs
CF Pages:     build: npm run build · output: dist/ · Node 20
VPS:          root@157.180.83.168 · agents at /root/agents/ · logs at /root/logs/
SSH key:      ~/.ssh/iim_vps (ed25519, never commit, chmod 600 before use)
MySQL (WP):   VPS 127.0.0.1:3306 · user iim_readonly · SELECT only — NEVER modify WP data
              Local access via SSH tunnel: ssh -i ~/.ssh/iim_vps -L 3307:127.0.0.1:3306 -N -f root@157.180.83.168
```

### Push agents to VPS
```bash
cd ~/dev/iimv2 && tar czf /tmp/agents.tar.gz agents/ \
  && scp -i ~/.ssh/iim_vps /tmp/agents.tar.gz root@157.180.83.168:/tmp/ \
  && ssh -i ~/.ssh/iim_vps root@157.180.83.168 \
       'tar xzf /tmp/agents.tar.gz -C /root/ && rm /tmp/agents.tar.gz' \
  && rm /tmp/agents.tar.gz

# If requirements.txt changed:
ssh -i ~/.ssh/iim_vps root@157.180.83.168 \
  "cd /root/agents && source venv/bin/activate && pip install -q -r requirements.txt"
```

### ~/.bashrc aliases (already set up)
```bash
alias iim-ssh="ssh -i ~/.ssh/iim_vps root@157.180.83.168"
alias iim-push-agents="..."   # compress → scp → decompress
alias iim-tunnel-open="ssh -i ~/.ssh/iim_vps -L 3307:127.0.0.1:3306 -N -f root@157.180.83.168"
alias iim-tunnel-close="pkill -f 'L 3307'"
```

---

## TECH STACK

```
Astro 4.x          SSG + minimal SSR for Observatory live pages
Keystatic CMS      Git-based CMS, browser UI for Anna's validation
Tailwind CSS       Styling
MDX                Article format
Zod                Content schema validation
@astrojs/i18n      Multilingual routing (en/fr/es/it)

Python 3.11+       Agent scripts (VPS via cron)
anthropic          Python SDK
feedparser         RSS parsing
requests           HTTP calls
mysql-connector-python  WP migration (read-only)
```

---

## SITE STRUCTURE

```
src/pages/
├── index.astro                   Homepage — positioning statement (NOT a blog listing)
├── observatory/
│   ├── index.astro               Data dashboard
│   ├── shutdown-tracker.astro    OONI + CF Radar chart, key events, monthly table
│   └── blocked-sites.astro
├── analysis/  (censorship/ · infrastructure/ · digital-economy/)
├── guides/    (vpn-circumvention/ · digital-security/ · connectivity/)
├── news/      (mobile/ · broadband/ · policy/)
└── about/     (mission.astro · anna-faure-revol.astro · partner.astro [draft until month 6])

src/data/                         ← written by VPS agents via GitHub API
├── ooni-history.json             OONI monthly (2021-02 → present)
├── ooni-history-weekly.json      OONI weekly (last 52 weeks)
├── ooni-history-daily.json       OONI daily (last 28 days)
├── cf-traffic.json               CF Radar traffic — monthly + weekly + daily
├── cf-radar-outages.json         Active CF Radar outages for Myanmar
├── bgp-history.json / bgp-outages.json
└── blocked-sites.json
```

---

## CONTENT SCHEMA

```typescript
const articles = defineCollection({
  schema: z.object({
    title:            z.string(),
    seoTitle:         z.string().max(60),
    metaDescription:  z.string().max(155),
    slug:             z.string(),
    category:         z.enum([
      'Censorship & Shutdowns', 'Telecom & Infrastructure', 'Digital Economy',
      'Guides & Tools', 'News - Mobile', 'News - Broadband', 'News - Policy',
    ]),
    tags:             z.array(z.string()),
    author:           z.string().default('Anna'),
    publishedAt:      z.date(),
    updatedAt:        z.date().optional(),
    draft:            z.boolean().default(true),
    featuredImage:    z.string().optional(),
    featuredImageAlt: z.string().max(100).optional(),
    excerpt:          z.string().max(300),
    readingTime:      z.number().optional(),
    lang:             z.enum(['en','fr','es','it']).default('en'),
    translationOf:    z.string().optional(),
    sources:          z.array(z.string().url()).optional(),
    migrated:         z.boolean().default(false),
    originalUrl:      z.string().url().optional(),
  })
})
```

---

## SEO RULES — enforced by agents, never deviate

```
seoTitle:        max 60 chars — primary keyword first
metaDescription: max 155 chars — factual, light CTA
slug:            lowercase, hyphens only, no stop words, max 6 words
                 GOOD: "myanmar-vpn-block-mandalay-2026"
                 BAD:  "how-the-myanmar-junta-is-blocking-the-internet"
alt texts:       descriptive, max 10 words, ZERO keyword stuffing
H1:              matches or close variant of seoTitle
Internal links:  3-5 per article
Schema:          Article + Organization on every page
Canonical:       always set, especially migrated articles

FORBIDDEN: keyword stuffing · duplicate meta descriptions · generic slugs · multiple H1s
```

---

## DESIGN DIRECTION

Reference: OONI Explorer, Access Now, Citizen Lab. Data-forward, editorial, serious.

```
Colors:
  Background: #0A1628  Accent: #00D4C8  Warning: #F59E0B  Danger: #EF4444
  Text dark:  #E2E8F0  Text light: #1E293B

Typography:
  Headlines: DM Serif Display · Body: IBM Plex Sans · Data: IBM Plex Mono

Principles: mobile-first · dark mode default · Observatory stats from JSON · Anna byline on every article
```

---

## AGENTS ARCHITECTURE

Developed locally at `~/dev/iimv2/agents/` → deployed to VPS. Config in `agents/config.yaml`.

```
agents/
├── config.yaml              Models, token limits, sources, paths
├── requirements.txt
├── monitor.py               Daily: fetch sources, score items
├── brief_generator.py       Briefs from monitor output
├── writer.py                Full MDX articles from approved briefs
├── publisher.py             Commit MDX + open GitHub PR
├── ooni_watcher.py          OONI + CF Radar → Observatory JSON files (6 outputs)
├── bgp_monitor.py           BGP outage watcher → bgp-history.json, bgp-outages.json
├── bgp_classifier.py        Classifies BGP events (shutdown / incident / noise)
├── digest_scanner.py        Daily digest of OONI + CF Radar anomalies
├── telegram_bot.py          Telegram alert bot for active outages
├── recategorise_articles.py One-shot: rewrite article categories in bulk
├── migration/
│   ├── wp_scanner.py        Score WP articles (0-10)
│   ├── wp_migrator.py       WP HTML → clean MDX
│   └── redirect_generator.py  Generate _redirects
├── briefs/                  YYYY-MM-DD/[slug].md — awaiting Anna
├── approved/                YYYY-MM-DD/[slug].md — triggers writer.py
└── utils/  (anthropic_client, github_client, mdx_formatter, token_rules)
```

### VPS crontab (current)
```
30 6    * * *  monitor.py          → briefs
0  8,20 * * *  ooni_watcher.py     → Observatory JSON
*/5 *   * * *  bgp_monitor.py --critical-only
*/30 *  * * *  bgp_monitor.py
0  8    * * *  digest_scanner.py
```

### Daily workflow
```
6:30 AM  Agents run → briefs in agents/briefs/YYYY-MM-DD/
Morning  Anna reviews briefs → approve (move to approved/) or delete
On demand  claude "Write articles for approved briefs in today's folder"
           → writer.py → MDX + GitHub PR "Draft: [title]"
Anna     Keystatic → review → draft:false → merge → live in 90s
```

---

## WORDPRESS MIGRATION

### Scoring (wp_scanner.py)
```
40% — Myanmar internet freedom / censorship / digital rights relevance
25% — Telecom / connectivity infrastructure relevance
20% — Quality: >800 words, has sources, substantive
15% — Not outdated / fits new brand

>= 7.0 → MIGRATE · 5-6.9 → FLAG FOR ANNA · < 5.0 → DISCARD
```

### Hard discard (no exceptions)
```
→ All crypto articles · All travel articles
→ All "Myanmar Geek" articles unless score >= 8
→ Guest posts from "TurnOnVPN" / "Miss PR"
→ Articles under 400 words
```

### HTML → MDX rules
```
→ Strip inline styles, Gutenberg comments, WP shortcodes
→ Rewrite ALL alt texts: descriptive, max 10 words, zero keyword stuffing
→ Update internal links to new URL structure
→ Convert image paths → /images/[slug]/[filename].webp
→ Set author: "Anna" · Add stale notice for articles > 18 months old
→ Add sources section · Reassign category from approved list
```

### Redirects
```
Migrated:  /old-wp-slug/ → /new-astro-slug  301
Discarded: /old-wp-slug/ → /               301
Output: public/_redirects (Cloudflare Pages format) · Zero 404s.
```

---

## MCP SERVERS

`.mcp.json` (repo root) — servers already installed globally in WSL:
```json
{
  "mcpServers": {
    "github":   { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
                  "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}" } },
    "fetch":    { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-fetch"] },
    "mysql":    { "command": "npx", "args": ["-y", "@benborla29/mcp-server-mysql"],
                  "env": { "MYSQL_HOST": "127.0.0.1", "MYSQL_PORT": "3307",
                            "MYSQL_USER": "iim_readonly", "MYSQL_PASS": "${WP_DB_PASSWORD_READONLY}",
                            "MYSQL_DB": "${WP_DB_NAME}",
                            "ALLOW_INSERT_OPERATION": "false", "ALLOW_UPDATE_OPERATION": "false",
                            "ALLOW_DELETE_OPERATION": "false" } },
    "sequential-thinking": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"] }
  }
}
```

`.env` keys (never commit): `ANTHROPIC_API_KEY` · `GITHUB_TOKEN` · `WP_DB_NAME` · `WP_DB_PASSWORD_READONLY` · `CLOUDFLARE_API_TOKEN` · `CLOUDFLARE_ACCOUNT_ID`

---

## ABSOLUTE RULES — NEVER VIOLATE

```
→ draft: false is set only by Anna — never by agents or Claude Code
→ Author is always "Anna" — never Myanmar Geek, Herbert Kanale
→ Never commit .env or any file with secrets
→ Never push directly to main — always via PR
→ Never write keyword-stuffed alt texts
→ Never modify the WordPress database — SELECT only
→ Never auto-publish without an Anna-approved brief
→ Never migrate crypto or travel articles
→ Never generate more output than the task requires
```

---

## EXECUTION PHASES

### Phase 1 — Build the site ✅ Complete
Remaining: WP migration (wp_scanner → Anna review → wp_migrator → _redirects) · DNS switch

### Phase 2 — Agents
```
✅ ooni_watcher.py → Observatory live data (OONI + CF Radar, all scales)
✅ monitor.py + brief_generator.py
✅ Deploy agents to VPS + crontab (bgp_monitor, digest_scanner also running)
✅ VPS GitHub SSH deploy key
   writer.py + publisher.py (deployed, not yet in production pipeline)
   Full pipeline test end-to-end · Anna validates first pipeline article
```

### Phase 3 — Growth (month 4-6)
```
1. French translations of top 5 articles
2. First quarterly report (PDF)
3. /about/partner/ page goes live
4. Outreach to RSF, JX Fund, OTF
```
