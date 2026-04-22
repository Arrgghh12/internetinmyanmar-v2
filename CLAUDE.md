# CLAUDE.md — Internet in Myanmar v2
# Project context — read entirely before any action
# Last updated: 2026-04-07

---

## TOKEN EFFICIENCY — READ THIS FIRST

### Claude Code (interactive sessions)
```
DO:
→ Read only files relevant to the current task
→ Use grep/find to locate files instead of reading directories
→ Write complete files in one shot
→ Chain commands: cmd1 && cmd2 && cmd3
→ Use -q/--silent/--quiet flags where available

DO NOT:
→ Summarize what you are about to do — just do it
→ Explain what you just did — output speaks for itself
→ Ask questions if the answer is in CLAUDE.md
→ Re-read files already read in this session
→ Read config files (package.json, astro.config) on every session start
→ Show code then rewrite it — write it correctly once
```

### Python agents (automated, no human in loop)
```python
SYSTEM_PROMPT = """Respond with the exact requested output only.
No preamble. No explanation. No 'Here is the result'.
No markdown fences unless output IS code.
First character of response = first character of actual output."""

# Model by task
MODELS = {
    "score":   "claude-haiku-4-5",   # classification → cheap
    "monitor": "claude-haiku-4-5",   # relevance check → cheap
    "brief":   "claude-sonnet-4-6",  # brief generation → balanced
    "write":   "claude-sonnet-4-6",  # full article → quality
    "seo":     "claude-haiku-4-5",   # meta/slug/tags → cheap
}

MAX_TOKENS = {
    "score":   150,   # JSON score object only
    "monitor": 300,   # relevance assessment
    "brief":   800,   # structured brief
    "write":   3000,  # full article
    "seo":     200,   # title + meta + slug
}
```

---

## FIRST SESSION — WSL2 Environment Check

Run this before anything else. Report findings, fix issues, then proceed.

```bash
# 1. Verify WSL2 (not WSL1)
wsl --status && wsl --list --verbose
# VERSION column must show 2 — if 1: wsl --set-version Ubuntu 2

# 2. Verify tools inside WSL
node --version    # need >= 20.x
npm --version     # need >= 10.x
python3 --version # need >= 3.11
git --version     # need >= 2.40
claude --version

# 3. Fix Node if outdated (use nvm, never apt for Node)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20 && nvm use 20 && nvm alias default 20

# 4. Fix Python if needed
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# 5. WSL performance — create C:\Users\[WindowsUser]\.wslconfig
[wsl2]
memory=4GB
processors=2
swap=2GB

# 6. CRITICAL — always work inside WSL filesystem (not /mnt/c/)
# CORRECT:  ~/dev/iimv2
# WRONG:    /mnt/c/dev/iimv2  (10x slower, breaks npm watches)
# Windows access: \\wsl$\Ubuntu\home\[user]\dev\iimv2

# 7. Git identity
git config --global user.name "Arrgghh12"
git config --global user.email "mploton@gmail.com"
```

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
- Role: Rédactrice en chef / Editor-in-Chief
- Speciality: Myanmar, Southeast Asia, digital rights, media freedom
- Languages: French, English, Spanish, Italian
- LinkedIn: [ANNA_LINKEDIN_URL]
- **All published articles are bylined: Anna** (never "Anna" — surname not used on site)
- Author bio (article pages + About):
  "Anna is a journalist specializing in Myanmar's media landscape,
  digital rights, and internet freedom. She has closely followed the military
  junta's systematic censorship of online information since the 2021 coup."
- Tone: precise, analytical, never sensationalist.
  Credible to both technical audiences (OONI, Citizen Lab)
  and institutional ones (RSF, Freedom House, JX Fund).
- Anna is the public face. She validates all briefs and publishes all articles.

### Technical Director (stays anonymous)
- Manages infrastructure, Claude Code pipeline, VPS agents
- Does not appear publicly on the site

### Former WP authors — do not carry over
- "Myanmar Geek"  → retired pseudonym
- "Herbert Kanale" → retired
- "Miss PR"        → one-off guest post, discard

---

## MULTILINGUAL STRATEGY

Anna's languages open four content tracks — she decides what gets translated.

```
English  → primary, all articles published here first
French   → key investigative pieces — targets RSF (French org), francophone donors
Spanish  → selected pieces — targets FLIP, Spanish-language press freedom orgs
Italian  → occasional — European institutional outreach
```

Implementation: Astro i18n routing.
Agents produce machine-translation draft → Anna reviews and edits.
Not every article needs all languages. Anna decides per article.

---

## INFRASTRUCTURE

```
Development:
  Machine:    Windows 11 + WSL2 Ubuntu
  Repo:       ~/dev/iimv2  ← inside WSL filesystem (not /mnt/c/)
  Dev server: localhost:4321

Version control:
  GitHub:     Arrgghh12/internetinmyanmar-v2
  Branches:
    main    → auto-deploy to Cloudflare Pages (production)
    dev     → dev.internetinmyanmar.com (Cloudflare Pages preview)
    draft/* → one per article, opened by VPS agents

Cloudflare Pages:
  Project:          internetinmyanmar-v2
  Production:       main    → internetinmyanmar.com      (after DNS switch)
  Preview:          dev     → dev.internetinmyanmar.com  (active now)
  Preview auto:     draft/* → [hash].internetinmyanmar-v2.pages.dev
  Build command:    npm run build
  Output dir:       dist/
  Node version:     20 (set in CF env vars)

VPS (CloudPanel, Ubuntu 22):
  Purpose:     Python agents ONLY — not the website itself
  Agents user: root
  Agents path: /root/agents/
  Logs:        /root/logs/

SSH ACCESS (how Claude Code connects to VPS):
  Key location: ~/.ssh/iim_vps
  SSH key is ed25519, already on disk in WSL home.
  DO NOT copy the key elsewhere. DO NOT commit it.

  SSH command pattern:
    ssh -i ~/.ssh/iim_vps \
        -o StrictHostKeyChecking=no \
        root@157.180.83.168

  SCP command pattern (push files to VPS):
    scp -i ~/.ssh/iim_vps \
        -r ~/dev/iimv2/agents/ \
        root@157.180.83.168:/root/agents/

  Before using SSH, verify key permissions (WSL requires this):
    chmod 600 ~/.ssh/iim_vps

MySQL (VPS — WordPress DB):
  Host:     127.0.0.1  ← use IP, not localhost, for Python mysql connector
  Port:     3306
  DB:       [WP_DB_NAME]
  User:     iim_readonly
  Password: [WP_DB_PASSWORD_READONLY]
  Rule:     SELECT only — NEVER modify WordPress data
```

---

## VPS — DEPLOYING AGENTS

Claude Code pushes the agents folder to the VPS via SCP, then
configures the environment remotely via SSH. Do this in sequence:

```bash
# Step 1 — Fix SSH key permissions (WSL requirement)
chmod 600 ~/.ssh/iim_vps

# Step 2 — Push agents folder to VPS (compress → scp → decompress)
cd ~/dev/iimv2 && tar czf /tmp/agents.tar.gz agents/ \
  && scp -i ~/.ssh/iim_vps /tmp/agents.tar.gz root@157.180.83.168:/tmp/ \
  && ssh -i ~/.ssh/iim_vps root@157.180.83.168 \
       'tar xzf /tmp/agents.tar.gz -C /root/ && rm /tmp/agents.tar.gz' \
  && rm /tmp/agents.tar.gz

# Step 3 — Push .env to VPS (agents need it, never in repo)
scp -i ~/.ssh/iim_vps \
    ~/dev/iimv2/.env \
    root@157.180.83.168:/root/agents/.env

# Step 4 — Remote setup via SSH (run once)
ssh -i ~/.ssh/iim_vps \
    root@157.180.83.168 << 'EOF'

  # Create venv and install dependencies
  cd ~/agents
  python3.11 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt

  # Create logs directory
  mkdir -p ~/logs

  # Set up GitHub SSH deploy key on VPS
  # (VPS needs its own key to push draft branches to GitHub)
  if [ ! -f ~/.ssh/github_deploy ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/github_deploy \
               -C "vps-agents@internetinmyanmar.com" -N ""
    echo "--- COPY THIS PUBLIC KEY TO GITHUB DEPLOY KEYS ---"
    cat ~/.ssh/github_deploy.pub
    echo "--- GitHub: repo Settings → Deploy keys → Add key (write access) ---"
  fi

  # Configure git to use VPS deploy key for GitHub
  git config --global core.sshCommand \
    "ssh -i ~/.ssh/github_deploy -o StrictHostKeyChecking=no"

  # Install crontab
  (crontab -l 2>/dev/null; echo "30 6 * * * ~/agents/venv/bin/python ~/agents/monitor.py >> ~/logs/monitor.log 2>&1") | crontab -
  (crontab -l 2>/dev/null; echo "0 8,20 * * * ~/agents/venv/bin/python ~/agents/ooni_watcher.py >> ~/logs/ooni.log 2>&1") | crontab -

  echo "VPS setup complete."
EOF

# Step 5 — Verify agents run correctly
ssh -i ~/.ssh/iim_vps \
    root@157.180.83.168 \
    "cd ~/agents && source venv/bin/activate && python ooni_watcher.py --test"
```

### Updating agents after code changes

When you modify agent scripts locally, push the update:

```bash
# Quick update — compress → scp → decompress
cd ~/dev/iimv2 && tar czf /tmp/agents.tar.gz agents/ \
  && scp -i ~/.ssh/iim_vps /tmp/agents.tar.gz root@157.180.83.168:/tmp/ \
  && ssh -i ~/.ssh/iim_vps root@157.180.83.168 \
       'tar xzf /tmp/agents.tar.gz -C /root/ && rm /tmp/agents.tar.gz' \
  && rm /tmp/agents.tar.gz

# If requirements.txt changed, also run pip install remotely:
ssh -i ~/.ssh/iim_vps \
    root@157.180.83.168 \
    "cd ~/agents && source venv/bin/activate && pip install -q -r requirements.txt"
```

---

## DATABASE CONNECTION

Used during migration (local Claude Code session via SSH tunnel)
and by agents running on the VPS (direct local connection).

### From Claude Code on your PC (SSH tunnel)

Claude Code cannot connect directly to the VPS MySQL from your PC.
Use an SSH tunnel to forward the remote port locally:

```bash
# Open tunnel in background (run once per session)
ssh -i ~/.ssh/iim_vps \
    -L 3307:127.0.0.1:3306 \
    -N -f \
    root@157.180.83.168

# Now connect locally on port 3307
# migration scripts use: host=127.0.0.1, port=3307
```

The migration scripts in `agents/migration/` must use:
```python
# agents/migration/db_config.py
import os
from dotenv import load_dotenv
load_dotenv()

# When running locally (via SSH tunnel):
LOCAL_DB = {
    "host":     "127.0.0.1",
    "port":     3307,          # tunneled port
    "database": os.getenv("WP_DB_NAME"),
    "user":     os.getenv("WP_DB_USER"),      # iim_readonly
    "password": os.getenv("WP_DB_PASSWORD_READONLY"),
}

# When running on VPS (agents, direct connection):
VPS_DB = {
    "host":     "127.0.0.1",   # use IP, not 'localhost'
    "port":     3306,
    "database": os.getenv("WP_DB_NAME"),
    "user":     os.getenv("WP_DB_USER"),
    "password": os.getenv("WP_DB_PASSWORD_READONLY"),
}

# Auto-detect environment
import socket
IS_VPS = socket.gethostname() != os.getenv("LOCAL_HOSTNAME", "")
DB_CONFIG = VPS_DB if IS_VPS else LOCAL_DB
```

### MCP MySQL server (for Claude Code interactive sessions)

The MySQL MCP also uses the SSH tunnel.
When tunnel is open on port 3307, the MCP config in `.mcp.json` uses:

```json
"mysql": {
  "command": "npx",
  "args": ["-y", "@benborla29/mcp-server-mysql"],
  "env": {
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_PORT": "3307",
    "MYSQL_USER": "iim_readonly",
    "MYSQL_PASS": "${WP_DB_PASSWORD_READONLY}",
    "MYSQL_DB": "${WP_DB_NAME}",
    "ALLOW_INSERT_OPERATION": "false",
    "ALLOW_UPDATE_OPERATION": "false",
    "ALLOW_DELETE_OPERATION": "false"
  }
}
```

### Opening and closing the tunnel (helper aliases)

Add to `~/.bashrc` in WSL — Claude Code can do this during setup:

```bash
# ~/.bashrc additions
VPS_KEY="~/.ssh/iim_vps"
VPS_HOST="root@157.180.83.168"

alias iim-tunnel-open="ssh -i $VPS_KEY -L 3307:127.0.0.1:3306 -N -f $VPS_HOST && echo 'Tunnel open on port 3307'"
alias iim-tunnel-close="pkill -f 'L 3307' && echo 'Tunnel closed'"
alias iim-ssh="ssh -i $VPS_KEY $VPS_HOST"
alias iim-push-agents="cd ~/dev/iimv2 && tar czf /tmp/agents.tar.gz agents/ && scp -i $VPS_KEY /tmp/agents.tar.gz $VPS_HOST:/tmp/ && ssh -i $VPS_KEY $VPS_HOST 'tar xzf /tmp/agents.tar.gz -C /root/ && rm /tmp/agents.tar.gz' && rm /tmp/agents.tar.gz"
```

Usage:
```bash
iim-tunnel-open   # open DB tunnel
iim-ssh           # SSH into VPS
iim-push-agents   # push updated agent scripts
iim-tunnel-close  # close tunnel when done
```

---

## TECH STACK

```
Astro 4.x                SSG + minimal SSR for Observatory live pages
Keystatic CMS            Git-based CMS, browser UI for Anna's validation
Tailwind CSS             Styling
MDX                      Article format
Zod                      Content schema validation
@astrojs/rss             RSS feed (important for ONG monitoring tools)
@astrojs/sitemap         Auto sitemap
astro-seo                Meta tags
schema-dts               Schema.org TypeScript types
@astrojs/i18n            Multilingual routing (en/fr/es/it)

Python 3.11+             Agent scripts (run on VPS via cron)
anthropic                Python SDK
feedparser               RSS parsing
requests                 HTTP calls
mysql-connector-python   WP migration (read-only)
python-dotenv            Env vars
```

---

## SITE STRUCTURE

### Navigation
```
Main nav:
  Reports & Analysis
    → Censorship & Shutdowns
    → Telecom & Infrastructure
    → Digital Economy
  Guides & Tools
    → VPN & Circumvention
    → Digital Security
    → Connectivity & SIM Cards
  Observatory
    → Shutdown Tracker
    → Blocked Sites Monitor
    → Quarterly Reports
  News
    → Mobile Networks
    → Broadband
    → Policy & Regulation
  About
    → Mission
    → Anna
    → Partner with Us  [draft:true — activate at month 6]

Utility bar (top):
  Coverage Map | Speedtest | Contact

Language switcher:
  EN | FR | ES | IT  (show only languages with content)
```

### Pages
```
src/pages/
├── index.astro              Homepage — positioning statement
│                            NOT a blog listing
│                            → live Observatory stats
│                            → featured analysis
│                            → latest news
│
├── observatory/
│   ├── index.astro          Data dashboard
│   ├── shutdown-tracker.astro
│   └── blocked-sites.astro
│
├── analysis/
│   ├── censorship/
│   ├── infrastructure/
│   └── digital-economy/
│
├── guides/
│   ├── vpn-circumvention/
│   ├── digital-security/
│   └── connectivity/
│
├── news/
│   ├── mobile/
│   ├── broadband/
│   └── policy/
│
└── about/
    ├── mission.astro
    ├── anna-faure-revol.astro   Author page with LinkedIn
    └── partner.astro            [draft:true until month 6]
```

---

## CONTENT SCHEMA

```typescript
// src/content/config.ts

const articles = defineCollection({
  schema: z.object({
    title:            z.string(),
    seoTitle:         z.string().max(60),
    metaDescription:  z.string().max(155),
    slug:             z.string(),
    category:         z.enum([
      'Censorship & Shutdowns',
      'Telecom & Infrastructure',
      'Digital Economy',
      'Guides & Tools',
      'News - Mobile',
      'News - Broadband',
      'News - Policy',
    ]),
    tags:             z.array(z.string()),
    author:           z.string().default('Anna'),
    publishedAt:      z.date(),
    updatedAt:        z.date().optional(),
    draft:            z.boolean().default(true), // humans publish, never agents
    featuredImage:    z.string().optional(),
    featuredImageAlt: z.string().max(100).optional(),
    excerpt:          z.string().max(300),
    readingTime:      z.number().optional(),
    lang:             z.enum(['en','fr','es','it']).default('en'),
    translationOf:    z.string().optional(), // slug of English original
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

alt texts:       descriptive sentence, max 10 words, ZERO keyword stuffing
                 GOOD: "Protesters in Mandalay with blocked phone screens"
                 BAD:  "Myanmar VPN censorship firewall junta block 2026"

H1:              matches or close variant of seoTitle
H2s:             include secondary keywords naturally
Internal links:  3-5 per article, descriptive anchor text
Schema:          Article + Organization on every page
Canonical:       always set, especially on migrated articles

FORBIDDEN:
→ Keyword stuffing in alt texts
→ Duplicate meta descriptions across articles
→ Generic or over-long slugs
→ Multiple H1 tags
```

---

## DESIGN DIRECTION

Reference: OONI Explorer, Access Now, Citizen Lab.
Data-forward, editorial, serious. A monitoring platform, not a blog.

```
Colors:
  Dark background:  #0A1628  (deep navy)
  Light background: #F8FAFC
  Accent:           #00D4C8  (teal — Observatory, data)
  Warning:          #F59E0B  (shutdown alerts)
  Danger:           #EF4444  (censorship events)
  Text on dark:     #E2E8F0
  Text on light:    #1E293B

Typography:
  Headlines: DM Serif Display  (authority, editorial)
  Body:      IBM Plex Sans     (technical credibility)
  Data/mono: IBM Plex Mono     (Observatory numbers)

Principles:
→ Homepage is a positioning statement, not an article listing
→ Observatory stats feel live (from JSON, not hardcoded)
→ Mobile-first — many readers on mobile in Myanmar/Thailand diaspora
→ Anna's byline + photo on every article
→ Dark mode default, light mode available
→ Core Web Vitals: LCP < 2.5s (Astro SSG handles this)
```

---

## AGENTS ARCHITECTURE

Developed locally at `~/dev/iimv2/agents/` → deployed to VPS

```
agents/
├── config.yaml
├── requirements.txt
├── monitor.py           Daily: fetch all sources, score items
├── brief_generator.py   Generate article briefs from monitor output
├── writer.py            Write full MDX articles from approved briefs
├── publisher.py         Commit MDX + open GitHub PR
├── ooni_watcher.py      OONI API → update Observatory JSON files
├── migration/
│   ├── wp_scanner.py        Score all WP articles
│   ├── wp_migrator.py       WP HTML → clean MDX
│   └── redirect_generator.py  Generate _redirects
├── briefs/              Agent output — awaiting Anna's review
│   └── YYYY-MM-DD/[slug].md
├── approved/            Anna-approved — trigger writer.py
│   └── YYYY-MM-DD/[slug].md
└── utils/
    ├── anthropic_client.py
    ├── github_client.py
    ├── mdx_formatter.py
    └── token_rules.py
```

### agents/config.yaml
```yaml
anthropic:
  models:
    score:   claude-haiku-4-5
    monitor: claude-haiku-4-5
    brief:   claude-sonnet-4-6
    write:   claude-sonnet-4-6
    seo:     claude-haiku-4-5
  max_tokens:
    score:   150
    monitor: 300
    brief:   800
    write:   3000
    seo:     200

sources:
  ooni_api:      "https://api.ooni.io/api/v1/measurements?probe_cc=MM&limit=100"
  rsf:           "https://rsf.org/en/rss/myanmar"
  netblocks:     "https://netblocks.org/tag/myanmar/feed"
  access_now:    "https://www.accessnow.org/category/blog/feed/"
  dvb:           "https://english.dvb.no/feed"
  irrawaddy:     "https://www.irrawaddy.com/feed"
  freedom_house: "https://freedomhouse.org/reports/freedom-net/feed"

scoring:
  min_score_for_brief: 6.0

article:
  author:       "Anna"
  default_lang: "en"
  target_words: [1200, 1800]
  internal_links: [3, 5]

github:
  repo:         "Arrgghh12/internetinmyanmar-v2"
  base_branch:  "dev"
  draft_prefix: "draft/"

paths:
  briefs:      "~/dev/iimv2/agents/briefs"
  approved:    "~/dev/iimv2/agents/approved"
  articles:    "~/dev/iimv2/src/content/articles"
  observatory: "~/dev/iimv2/src/content/observatory"
```

### VPS crontab (as agents user)
```bash
# Monitor + brief generation at 6:30 AM
30 6 * * * ~/agents/venv/bin/python ~/agents/monitor.py >> ~/logs/monitor.log 2>&1

# OONI Observatory update at 8 AM and 8 PM
0 8,20 * * * ~/agents/venv/bin/python ~/agents/ooni_watcher.py >> ~/logs/ooni.log 2>&1
```

### Daily workflow
```
6:30 AM  Agents run on VPS automatically
         → sources fetched, items scored
         → briefs created in agents/briefs/YYYY-MM-DD/

Morning  Anna reads briefs (plain markdown, readable anywhere)
         → approve: move to agents/approved/YYYY-MM-DD/
           can edit brief to adjust angle or add context
         → reject: delete

When ready — Anna or technical director runs:
  claude "Write articles for approved briefs in today's folder"
         → writer.py generates full MDX with Anna's byline
         → GitHub PR opened: "Draft: [article title]"

Anna     Opens Keystatic in browser → reads rendered article
         → edits if needed
         → sets draft: false
         → merges PR → Cloudflare rebuilds → live in 90 seconds
```

---

## WORDPRESS MIGRATION

### Article scoring (wp_scanner.py)
```
Score 0-10:
  40% — Relevance to Myanmar internet freedom / censorship / digital rights
  25% — Relevance to telecom / connectivity infrastructure
  20% — Quality: >800 words, has sources, substantive
  15% — Not outdated / fits new brand positioning

Thresholds:
  >= 7.0 → MIGRATE
  5-6.9  → FLAG FOR ANNA'S REVIEW
  < 5.0  → DISCARD
```

### Hard discard rules (no exceptions)
```
→ All crypto articles (Luna, Bitcoin/MMK, passive income)
→ All travel articles (Yangon trips, Inle Lake, Laos SIM)
→ All "Myanmar Geek" articles unless score >= 8
→ Guest posts from "TurnOnVPN" / "Miss PR"
→ Articles under 400 words
```

### HTML → MDX conversion rules
```
→ Strip all inline styles and Gutenberg block comments
→ Remove all WordPress shortcodes
→ Rewrite ALL alt texts: descriptive, max 10 words, zero keyword stuffing
→ Update internal links to new URL structure
→ Convert image paths → /images/[slug]/[filename].webp
→ Set author: "Anna" on all migrated articles
→ Add stale notice for articles > 18 months old:
  "⚠️ First published in [YEAR]. Some figures may be outdated."
→ Add sources section at bottom from external links found in content
→ Reassign category from approved list
```

### 301 Redirects
```
Migrated:  /old-wp-slug/  →  /new-astro-slug  301
Discarded: /old-wp-slug/  →  /               301

Zero 404s. Every old URL must resolve.
Output file: public/_redirects (Cloudflare Pages format)
```

---

## MCP SERVERS

Install once in WSL:
```bash
npm install -g @modelcontextprotocol/server-github
npm install -g @modelcontextprotocol/server-fetch
npm install -g @benborla29/mcp-server-mysql
npm install -g @modelcontextprotocol/server-sequential-thinking
```

.mcp.json (repo root):
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}" }
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    },
    "mysql": {
      "command": "npx",
      "args": ["-y", "@benborla29/mcp-server-mysql"],
      "env": {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3307",
        "MYSQL_USER": "iim_readonly",
        "MYSQL_PASS": "${WP_DB_PASSWORD_READONLY}",
        "MYSQL_DB": "${WP_DB_NAME}",
        "ALLOW_INSERT_OPERATION": "false",
        "ALLOW_UPDATE_OPERATION": "false",
        "ALLOW_DELETE_OPERATION": "false"
      }
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

.env (never commit):
```bash
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
WP_DB_NAME=...
WP_DB_PASSWORD_READONLY=...
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
```

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

### Phase 1 — Build the site (now)
```
1.  WSL2 environment check and fix
2.  GitHub repo: internetinmyanmar-v2
3.  Astro 4 project at ~/dev/iimv2
4.  Keystatic CMS configuration
5.  Content schema (config.ts) with Zod
6.  Base layouts: Base, Article, Observatory
7.  Homepage (positioning statement)
8.  .mcp.json + MCP server installs
9.  MySQL read-only user on VPS
10. wp_scanner.py → scoring_report.md
11. Anna reviews scoring report
12. wp_migrator.py → MDX articles
13. redirect_generator.py → _redirects
14. Cloudflare Pages setup (connect GitHub)
15. DNS switch when ready
```

### Phase 2 — Agents (after site is live)
```
1. ooni_watcher.py → Observatory live data
2. monitor.py + brief_generator.py
3. writer.py + publisher.py
4. Deploy agents to VPS + crontab
5. VPS GitHub SSH deploy key
6. Full pipeline test end-to-end
7. Anna validates first pipeline article
```

### Phase 3 — Growth (month 4-6)
```
1. French translations of top 5 articles
2. First quarterly report (PDF)
3. /about/partner/ page goes live
4. Outreach to RSF, JX Fund, OTF
```
