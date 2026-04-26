"""
generate_election_snapshot.py
------------------------------
Generates a one-page PDF "Election Censorship Snapshot" for the article
myanmar-election-internet-censorship-2025-2026.

Charts:
  1. OONI anomaly rate timeline (Feb 2021 – Apr 2026), election phases marked
  2. Cloudflare Radar weekly traffic (Aug 2025 – Apr 2026), Feb routing shift marked
  3. Key services blocking rates (horizontal bar, grouped by category)

Output: public/assets/election-censorship-snapshot-2025-26.pdf

Usage:
  python agents/generate_election_snapshot.py           # generates PDF
  python agents/generate_election_snapshot.py --dry-run # renders HTML only (no PDF)

Run from repo root or VPS with DATA_PATH env set.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
AGENTS_DIR = Path(__file__).parent
_data_path_env = os.environ.get("DATA_PATH", "")
if _data_path_env:
    DATA_DIR = Path(_data_path_env)
    REPO_ROOT = DATA_DIR.parent.parent
else:
    REPO_ROOT = AGENTS_DIR.parent
    DATA_DIR = REPO_ROOT / "src" / "data"

OUTPUT_PDF  = REPO_ROOT / "public" / "assets" / "election-censorship-snapshot-2025-26.pdf"
OUTPUT_HTML = REPO_ROOT / "public" / "assets" / "election-censorship-snapshot-2025-26.html"
METRICS_JSON = REPO_ROOT / "public" / "data" / "metrics_snapshot.json"

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_ooni_monthly():
    path = DATA_DIR / "ooni-history.json"
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    return data.get("monthly", data.get("data", []))

def load_cf_weekly():
    path = DATA_DIR / "cf-traffic.json"
    data = json.loads(path.read_text())
    return data.get("weekly", [])

def load_blocked_sites():
    path = DATA_DIR / "blocked-sites.json"
    data = json.loads(path.read_text())
    return data.get("sites", [])

def load_metrics():
    if METRICS_JSON.exists():
        return json.loads(METRICS_JSON.read_text())
    return {}

# ---------------------------------------------------------------------------
# Build chart data
# ---------------------------------------------------------------------------

def ooni_chart_data(monthly):
    labels, rates, colors, phase_annotations = [], [], [], []

    election_start = "2025-11"
    phase1 = "2025-12"
    phase2 = "2026-01"
    post   = "2026-02"

    for row in monthly:
        m = row.get("month") or row.get("period", "")[:7]
        if not m:
            continue
        rate = row.get("anomaly_rate", 0)
        labels.append(m)
        rates.append(rate)
        if m < election_start:
            colors.append("rgba(148,163,184,0.5)")
        elif m == election_start:
            colors.append("rgba(251,191,36,0.7)")
        elif m in (phase1, phase2):
            colors.append("rgba(239,68,68,0.75)")
        else:
            colors.append("rgba(148,163,184,0.35)")

    return labels, rates, colors

def cf_chart_data(weekly):
    labels, values, colors = [], [], []
    for row in weekly:
        ts = row.get("timestamp", "")[:10]
        if ts < "2025-08-01":
            continue
        val = row.get("cf_traffic", 0)
        labels.append(ts)
        values.append(val)
        if ts >= "2026-02-01":
            colors.append("rgba(239,68,68,0.8)")
        elif ts >= "2025-11-01":
            colors.append("rgba(251,191,36,0.7)")
        else:
            colors.append("rgba(148,163,184,0.5)")
    return labels, values, colors

def blocked_chart_data(sites):
    category_order = ["Social Media", "News & Media", "VPN & Circumvention", "Civil Society"]
    category_colors = {
        "Social Media":         "rgba(239,68,68,0.85)",
        "News & Media":         "rgba(251,191,36,0.85)",
        "VPN & Circumvention":  "rgba(249,115,22,0.85)",
        "Civil Society":        "rgba(168,85,247,0.85)",
    }
    # Average rate per category
    cat_data = {c: [] for c in category_order}
    for s in sites:
        cat = s.get("category", "")
        if cat in cat_data:
            cat_data[cat].append(s.get("rate", 0))
    labels, averages, bg_colors = [], [], []
    for cat in category_order:
        vals = cat_data[cat]
        if vals:
            labels.append(cat)
            averages.append(round(sum(vals) / len(vals), 1))
            bg_colors.append(category_colors[cat])
    return labels, averages, bg_colors


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

def build_html(ooni_monthly, cf_weekly, blocked_sites, metrics):
    o_labels, o_rates, o_colors   = ooni_chart_data(ooni_monthly)
    cf_labels, cf_vals, cf_colors = cf_chart_data(cf_weekly)
    b_labels, b_avgs, b_colors    = blocked_chart_data(blocked_sites)

    dataset_version = metrics.get("dataset_version", "v2026.04.26")
    generated_at    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_events    = metrics.get("total_shutdown_events", 95)
    impact_days     = metrics.get("shutdown_impact_days_total", 0)
    impact_years    = round(impact_days / 365, 0) if impact_days else "—"

    # Inject data as JSON for Chart.js
    o_labels_json  = json.dumps(o_labels)
    o_rates_json   = json.dumps(o_rates)
    o_colors_json  = json.dumps(o_colors)
    cf_labels_json = json.dumps(cf_labels)
    cf_vals_json   = json.dumps(cf_vals)
    cf_colors_json = json.dumps(cf_colors)
    b_labels_json  = json.dumps(b_labels)
    b_avgs_json    = json.dumps(b_avgs)
    b_colors_json  = json.dumps(b_colors)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Myanmar Election 2025–2026: Censorship Snapshot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'IBM Plex Sans', Arial, sans-serif;
    background: #fff;
    color: #1e293b;
    width: 210mm;
    min-height: 297mm;
    padding: 14mm 16mm 12mm;
  }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 3px solid #00D4C8;
    padding-bottom: 10px;
    margin-bottom: 14px;
  }}
  .header-left h1 {{
    font-size: 20px;
    font-weight: 700;
    color: #0A1628;
    line-height: 1.2;
  }}
  .header-left .subtitle {{
    font-size: 11px;
    color: #64748b;
    margin-top: 3px;
  }}
  .header-right {{
    text-align: right;
    font-size: 10px;
    color: #94a3b8;
    line-height: 1.6;
  }}
  .header-right .logo {{
    font-size: 11px;
    font-weight: 600;
    color: #0A1628;
  }}

  /* Key findings strip */
  .findings {{
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
  }}
  .finding-card {{
    flex: 1;
    background: #f8fafc;
    border-left: 3px solid #00D4C8;
    padding: 7px 10px;
    border-radius: 0 4px 4px 0;
  }}
  .finding-card .value {{
    font-size: 22px;
    font-weight: 700;
    color: #0A1628;
    line-height: 1;
  }}
  .finding-card .label {{
    font-size: 9.5px;
    color: #64748b;
    margin-top: 2px;
    line-height: 1.3;
  }}
  .finding-card.alert .value {{ color: #ef4444; }}
  .finding-card.warn  .value {{ color: #f59e0b; }}
  .finding-card.teal  .value {{ color: #00D4C8; }}

  /* Charts */
  .charts-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
    gap: 12px;
    margin-bottom: 14px;
  }}
  .chart-box {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px 12px;
  }}
  .chart-box.full-width {{
    grid-column: 1 / -1;
  }}
  .chart-box h3 {{
    font-size: 11px;
    font-weight: 600;
    color: #0A1628;
    margin-bottom: 3px;
  }}
  .chart-box .chart-note {{
    font-size: 9px;
    color: #64748b;
    margin-bottom: 6px;
    font-style: italic;
  }}
  canvas {{
    max-height: 160px;
  }}
  .chart-box.full-width canvas {{
    max-height: 130px;
  }}

  /* Legend pills */
  .legend {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 4px;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 8.5px;
    color: #475569;
  }}
  .legend-dot {{
    width: 8px; height: 8px;
    border-radius: 2px;
    flex-shrink: 0;
  }}

  /* Callout box */
  .callout {{
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-left: 4px solid #f59e0b;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 10px;
    color: #78350f;
    margin-bottom: 14px;
    line-height: 1.5;
  }}
  .callout strong {{ color: #92400e; }}

  /* Downloads */
  .downloads {{
    background: #f0fdfa;
    border: 1px solid #99f6e4;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 12px;
  }}
  .downloads h3 {{
    font-size: 11px;
    font-weight: 600;
    color: #0A1628;
    margin-bottom: 7px;
  }}
  .download-links {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }}
  .dl-link {{
    background: #fff;
    border: 1px solid #5eead4;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 9.5px;
    font-family: 'IBM Plex Mono', monospace;
    color: #0f766e;
    text-decoration: none;
    font-weight: 500;
  }}

  /* Footer */
  .footer {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-top: 1px solid #e2e8f0;
    padding-top: 8px;
    font-size: 8.5px;
    color: #94a3b8;
    line-height: 1.6;
  }}
  .footer a {{ color: #00D4C8; text-decoration: none; }}

  @media print {{
    body {{ padding: 10mm 14mm; }}
  }}
</style>
</head>
<body>

<!-- ── Header ─────────────────────────────────────────────────── -->
<div class="header">
  <div class="header-left">
    <h1>Myanmar Election 2025–2026: Censorship Snapshot</h1>
    <div class="subtitle">Independent technical monitoring — OONI · Cloudflare Radar · BGP · KeepItOn/Access Now</div>
  </div>
  <div class="header-right">
    <div class="logo">internetinmyanmar.com</div>
    <div>Observatory · {generated_at}</div>
    <div>dataset {dataset_version}</div>
  </div>
</div>

<!-- ── Key Findings ───────────────────────────────────────────── -->
<div class="findings">
  <div class="finding-card alert">
    <div class="value">18.6%</div>
    <div class="label">OONI anomaly rate Dec 2025<br>(Phase 1 polling month — below Nov's 23.2%)</div>
  </div>
  <div class="finding-card warn">
    <div class="value">{total_events}</div>
    <div class="label">Verified internet shutdowns<br>in Myanmar 2025 (KeepItOn)</div>
  </div>
  <div class="finding-card alert">
    <div class="value">89%</div>
    <div class="label">Facebook OONI anomaly rate<br>during election period</div>
  </div>
  <div class="finding-card teal">
    <div class="value">~100%</div>
    <div class="label">Cloudflare Radar index<br>post-election (Feb–Apr 2026)</div>
  </div>
</div>

<!-- ── Callout ────────────────────────────────────────────────── -->
<div class="callout">
  <strong>Key Finding:</strong> Myanmar's OONI anomaly rate showed no election-day spike on December 28, January 11, or January 25. The junta did not need emergency blackouts — a pre-existing censorship infrastructure blocking 60–90% of independent media, social platforms, and VPN services made acute shutdown actions unnecessary. This is <em>ambient censorship</em>: structural, continuous, and invisible to tools calibrated for acute disruption events.
</div>

<!-- ── Charts ─────────────────────────────────────────────────── -->
<div class="charts-grid">

  <!-- Chart 1: OONI Timeline — full width -->
  <div class="chart-box full-width">
    <h3>OONI Anomaly Rate — Monthly, Feb 2021 – Apr 2026</h3>
    <div class="chart-note">Share of network measurements returning anomalous results. Election phases: Campaign = Nov 2025, Phase 1 = Dec 2025, Phases 2–3 = Jan 2026.</div>
    <canvas id="chart-ooni"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#94a3b8"></div>Pre-election baseline</div>
      <div class="legend-item"><div class="legend-dot" style="background:#fbbf24"></div>Campaign period (Nov 2025)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>Voting phases (Dec 2025 – Jan 2026)</div>
    </div>
  </div>

  <!-- Chart 2: CF Radar -->
  <div class="chart-box">
    <h3>Cloudflare Radar Traffic Index — Weekly</h3>
    <div class="chart-note">Myanmar IP traffic via Cloudflare, 0–100 scale. Rise = VPN/circumvention surge; Feb 2026 spike = structural routing shift.</div>
    <canvas id="chart-cf"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#94a3b8"></div>Baseline (Aug–Oct 2025)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#fbbf24"></div>Election period (Nov 2025–Jan 2026)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>Post-election routing shift (Feb 2026+)</div>
    </div>
  </div>

  <!-- Chart 3: Blocking by category -->
  <div class="chart-box">
    <h3>Average OONI Blocking Rate by Category</h3>
    <div class="chart-note">Mean anomaly rate across {len(blocked_sites)} tracked domains, grouped by category. Source: OONI Web Connectivity.</div>
    <canvas id="chart-blocked"></canvas>
  </div>

</div>

<!-- ── Downloads ─────────────────────────────────────────────── -->
<div class="downloads">
  <h3>Download the underlying datasets (CC BY 4.0 · internetinmyanmar.com)</h3>
  <div class="download-links">
    <a class="dl-link" href="https://internetinmyanmar.com/data/ooni_timeseries.csv">ooni_timeseries.csv</a>
    <a class="dl-link" href="https://internetinmyanmar.com/data/keepiton_shutdowns.csv">keepiton_shutdowns.csv</a>
    <a class="dl-link" href="https://internetinmyanmar.com/data/bgp_events.csv">bgp_events.csv</a>
    <a class="dl-link" href="https://internetinmyanmar.com/data/unified_events.json">unified_events.json</a>
  </div>
</div>

<!-- ── Footer ────────────────────────────────────────────────── -->
<div class="footer">
  <div>
    OONI data CC BY 4.0 · Cloudflare Radar CC BY-NC 4.0 · KeepItOn/Access Now<br>
    Cite as: <em>Internet in Myanmar Observatory, internetinmyanmar.com, {generated_at}</em>
  </div>
  <div style="text-align:right">
    Full article &amp; interactive charts:<br>
    <a href="https://internetinmyanmar.com/articles/myanmar-election-internet-censorship-2025-2026/">internetinmyanmar.com/articles/myanmar-election-internet-censorship-2025-2026/</a>
  </div>
</div>

<!-- ── Chart.js ──────────────────────────────────────────────── -->
<script>
const ooniLabels  = {o_labels_json};
const ooniRates   = {o_rates_json};
const ooniColors  = {o_colors_json};
const cfLabels    = {cf_labels_json};
const cfVals      = {cf_vals_json};
const cfColors    = {cf_colors_json};
const bLabels     = {b_labels_json};
const bAvgs       = {b_avgs_json};
const bColors     = {b_colors_json};

const baseFont = {{ family: "'IBM Plex Sans', Arial, sans-serif", size: 9 }};
Chart.defaults.font = baseFont;
Chart.defaults.color = '#475569';

// Chart 1 — OONI timeline
new Chart(document.getElementById('chart-ooni'), {{
  type: 'bar',
  data: {{
    labels: ooniLabels,
    datasets: [{{
      data: ooniRates,
      backgroundColor: ooniColors,
      borderRadius: 2,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.y}}% anomaly rate`
        }}
      }},
      annotation: {{ annotations: [] }}
    }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 16, maxRotation: 45, font: {{ size: 7.5 }} }}, grid: {{ display: false }} }},
      y: {{
        min: 0, max: 40,
        ticks: {{ callback: v => v + '%', stepSize: 10, font: {{ size: 8 }} }},
        grid: {{ color: 'rgba(0,0,0,0.05)' }}
      }}
    }}
  }}
}});

// Chart 2 — CF Radar
// Format x labels to shorter form
const cfShortLabels = cfLabels.map(l => l.slice(5)); // MM-DD

new Chart(document.getElementById('chart-cf'), {{
  type: 'line',
  data: {{
    labels: cfShortLabels,
    datasets: [{{
      data: cfVals,
      borderColor: '#00D4C8',
      borderWidth: 2,
      pointBackgroundColor: cfColors,
      pointRadius: 3,
      fill: true,
      backgroundColor: 'rgba(0,212,200,0.08)',
      tension: 0.3,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.y}}% traffic index`
        }}
      }}
    }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 10, maxRotation: 45, font: {{ size: 7 }} }}, grid: {{ display: false }} }},
      y: {{
        min: 0, max: 110,
        ticks: {{ callback: v => v + '%', stepSize: 25, font: {{ size: 8 }} }},
        grid: {{ color: 'rgba(0,0,0,0.05)' }}
      }}
    }}
  }}
}});

// Chart 3 — Blocking by category
new Chart(document.getElementById('chart-blocked'), {{
  type: 'bar',
  data: {{
    labels: bLabels,
    datasets: [{{
      data: bAvgs,
      backgroundColor: bColors,
      borderRadius: 3,
      borderSkipped: false,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.x}}% avg anomaly rate`
        }}
      }}
    }},
    scales: {{
      x: {{
        min: 0, max: 100,
        ticks: {{ callback: v => v + '%', font: {{ size: 8 }} }},
        grid: {{ color: 'rgba(0,0,0,0.05)' }}
      }},
      y: {{ ticks: {{ font: {{ size: 9 }} }}, grid: {{ display: false }} }}
    }}
  }}
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

async def generate(dry_run: bool = False):
    ooni_monthly  = load_ooni_monthly()
    cf_weekly     = load_cf_weekly()
    blocked_sites = load_blocked_sites()
    metrics       = load_metrics()

    html = build_html(ooni_monthly, cf_weekly, blocked_sites, metrics)

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"HTML written → {OUTPUT_HTML}")

    if dry_run:
        print("Dry run — HTML only, no PDF.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"file://{OUTPUT_HTML.resolve()}", wait_until="networkidle")
        await page.pdf(
            path=str(OUTPUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        await browser.close()

    print(f"PDF written  → {OUTPUT_PDF}")
    print(f"Size: {OUTPUT_PDF.stat().st_size // 1024} KB")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(generate(dry_run=dry_run))
