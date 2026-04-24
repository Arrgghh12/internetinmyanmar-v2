# Cloudflare Radar — Observatory Integration Options

## What Cloudflare Radar has that we don't

Current stack covers:
- **OONI** → website-level blocking tests (sample-based, user-initiated)
- **RIPE RIS** → BGP route visibility/withdrawals (routing table health)
- **IODA** → cross-validation of BGP outages

Cloudflare Radar unique additions for Myanmar (MM):

| CF Radar capability | What it sees | Current gap |
|---|---|---|
| **Traffic anomaly detection** | Actual HTTP/DNS request volume drops — statistically detected every 15 min | OONI tests anomalies, RIPE sees routes — neither sees real traffic volume |
| **Outage annotations** | Verified outage events with timestamps, affected ASNs, cause labels — CF team manually reviews | We derive outages from BGP math; CF confirms them independently |
| **Internet Quality** | Latency, download/upload speed, jitter by ASN (from speed.cloudflare.com tests) | Zero performance data in current stack |
| **BGP hijacks & route leaks** | Unauthorized origin announcements + provider-customer path violations | BGP page tracks withdrawals/visibility but not hijacks or leaks |
| **DDoS attacks** (L3/4 and L7) | Attack traffic targeting or originating from Myanmar, by ISP | Not in current stack at all |
| **DNS query patterns** | Query volume and distribution from CF's 1.1.1.1 resolver | Not tracked |

---

## Option 1 — Outage confirmation widget on existing pages

**Rating: ★★★★★ — do this first**

### What it does
Add a single lightweight API call to `/radar/annotations/outages?location=MM` and surface it
as a status banner on the Observatory index and Shutdown Tracker.

- When CF has a verified outage event active → show:
  > "Cloudflare Radar: active disruption confirmed on [ASN name] since [time]."
- When no active outage → show nothing (or a subtle "CF: no active disruption detected")

### Why top rated
- Near zero implementation effort — one API call, one conditional banner
- Massive credibility boost: when OONI + RIPE + CF all independently agree, the evidence
  is airtight
- CF's annotations are human-verified, not just algorithmic — they carry weight with
  journalists and NGOs (RSF, Freedom House, Citizen Lab)
- Plugs directly into existing pages with no new navigation
- The outage data includes cause labels (POWER_OUTAGE, WEATHER, etc.) — useful editorial
  context Anna can reference in articles

### What it doesn't do
No ongoing historical chart, no new data dimensions — purely a live confirmation signal.

### Implementation
- Agent: one new function in `ooni_watcher.py` calling CF Radar outages endpoint
- Frontend: conditional banner component added to `/observatory/index.astro` and
  `/observatory/shutdown-tracker.astro`
- Effort: ~half a day

---

## Option 2 — Enhance Shutdown Tracker with CF traffic volume timeseries

**Rating: ★★★★☆**

### What it does
The Shutdown Tracker currently shows OONI anomaly rates per month. Add a second data layer:
CF Radar's normalized traffic volume for Myanmar (`/radar/netflows/summary_v2?location=MM`),
plotted as a secondary line on the existing chart or as a panel directly below it.

### Why strong
- Shows **two independent methodologies** agreeing on the same shutdown events:
  - OONI tests individual sites → website-level
  - CF sees total traffic volume → network-level
  - A spike in OONI anomalies + simultaneous CF traffic drop = high-confidence shutdown
- Same page, same context, no new navigation needed
- Traffic data updates every ~15 min; the page already rebuilds twice daily — cadence matches
- CF Radar traffic data for Myanmar has been cited in academic papers on internet shutdowns
- Directly strengthens Anna's credibility when publishing analysis pieces

### Complexity
Medium. `ooni_watcher.py` needs a second CF API call; the Shutdown Tracker chart needs a
second dataset overlay (Chart.js already in use on the BGP page — reuse that pattern).

### Risk
- CF traffic data may have lower confidence for smaller ASNs
- Data licence is CC BY-NC 4.0 — fine for this mission, attribution required on page

### Implementation
- Agent: one new CF API call in `ooni_watcher.py`, output appended to `ooni-history.json`
  or a new `cf-traffic.json`
- Frontend: second dataset on the existing SVG/Chart.js bar chart in
  `/observatory/shutdown-tracker.astro`
- Effort: ~1–2 days

---

## Option 3 — New "Internet Quality" page

**Rating: ★★★☆☆**

### What it does
New `/observatory/quality/` page pulling CF Radar's Internet Quality metrics:
latency, download/upload speed, jitter — broken down by the major Myanmar ISPs
(MPT, Ooredoo, Mytel, SkyNet). Updated via the existing cron agent.

### Why useful
- Currently zero performance data in the stack — fills a genuine gap
- Latency degradation is a subtler form of throttling than outright blocking.
  CF data would let us document **slowdowns** (common junta tactic) not just shutdowns
- Attractive to the technical audience (OONI, Citizen Lab, researchers studying throttling)
- Each ISP gets its own row → clear visual of which operators are degrading service vs.
  which are blocking entirely

### Why not higher rated
- Quality metrics are 90-day rolling averages, not event-based — less dramatic/actionable
- Depends on users in Myanmar actually running speed.cloudflare.com tests — data may be thin
  for some ISPs
- Doesn't directly advance the censorship/shutdown mission as urgently as Options 1 and 2
- More useful as a long-term trend resource than a real-time alert tool

### Implementation
- New `/observatory/quality/` page
- New agent call fetching `/radar/quality` per ASN
- Simple table + sparkline chart per ISP
- Effort: ~1 day

---

## Option 4 — Enhance BGP page with hijack and route leak detection

**Rating: ★★★☆☆**

### What it does
The BGP page already tracks route withdrawals. Add a new section using:
- `/radar/bgp/hijacks/events` (filtered to Myanmar ASNs)
- `/radar/bgp/leaks/events` (filtered to Myanmar ASNs)

Show a table of detected events with: confidence score, affected prefix, suspected origin AS,
timestamp.

### Why useful
- BGP hijacking is a known tool of state control — the junta has the technical means;
  China and Russia have used it as a censorship mechanism
- Route leaks reveal routing topology that shouldn't be public — intelligence value for
  researchers at Citizen Lab, OONI, Censored Planet
- Natural fit: same page, same audience, same "BGP" mental model
- CF hijack detection uses a different algorithm than RIPE — independent signal

### Why not higher rated
- Myanmar hasn't had documented BGP hijacking incidents yet — building for a future threat
- Hijack/leak events for a small-traffic country may be sparse — table could look empty
  for long periods
- More relevant to technical researchers than journalists or activists (narrower audience)

### Implementation
- Two new API calls in the BGP watcher (`bgp_watcher.py` or `ooni_watcher.py`)
- One new table section on `/observatory/bgp.astro` — minimal frontend work
- Effort: ~half a day for the section; value increases if/when an incident occurs

---

## Option 5 — Standalone "Cloudflare Radar Dashboard" page

**Rating: ★★☆☆☆**

### What it does
A new `/observatory/radar/` page embedding or replicating the full CF Radar view for
Myanmar: traffic volume, quality, attacks, BGP events, DNS — all in one place.

### Why it falls short
- Cloudflare already has `radar.cloudflare.com/MM` — a full, well-designed dashboard.
  Replicating it is redundant and positions us as a thin wrapper
- High implementation effort for incremental value over simply linking to CF Radar
- Data freshness risk: if we pull data twice-daily via cron, the page goes stale between
  runs; if we fetch client-side, the API key is exposed

### The one valid use case
If we embed CF's official `<iframe>` embeddable widgets (CF does offer these) rather than
building from scratch — effort drops significantly and this becomes more viable. But it
trades control for convenience.

---

## Recommendation — Phased approach

### Phase 1 (this week)
**Do Option 1.**
One call to `/radar/annotations/outages`, one banner. Shippable in an afternoon.
The credibility from having CF, OONI, and RIPE all independently confirming a shutdown
is the highest-value, lowest-cost thing available.

### Phase 2 (next sprint)
**Do Option 2.**
Add the CF traffic timeseries to the Shutdown Tracker as a second layer. This transforms
the page from "OONI anomaly chart" into "multi-source disruption corroboration tool" —
the kind of evidence RSF and Citizen Lab actually cite in their own reporting.

### Phase 3 (later, based on editorial direction)
- **Option 3** if Anna wants to document throttling as a tactic — it's underreported
  relative to full shutdowns and would differentiate the site
- **Option 4** if a hijacking incident actually occurs in Myanmar (reactive, not proactive)

### Skip
**Option 5** — Cloudflare's own dashboard does it better.

---

## Technical notes

- **API**: `https://api.cloudflare.com/client/v4/radar/`
- **Auth**: Free API token with `Account > Radar` (read) permissions
- **Licence**: CC BY-NC 4.0 — non-commercial use allowed, attribution required
- **Key endpoints for Myanmar**:
  ```
  /radar/annotations/outages?location=MM&dateRange=7d       # Option 1
  /radar/netflows/summary_v2?location=MM                    # Option 2
  /radar/quality?location=MM                                # Option 3
  /radar/bgp/hijacks/events                                 # Option 4
  /radar/bgp/leaks/events                                   # Option 4
  ```
- **Update cadence**: Outages ~15 min detection; traffic aggregates ~15 min;
  BGP tables every 2 hours; quality metrics 90-day rolling average
