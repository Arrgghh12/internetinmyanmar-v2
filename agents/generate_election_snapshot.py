"""
generate_election_snapshot.py
------------------------------
Generates a one-page PDF "Election Censorship Snapshot" for the article
myanmar-election-internet-censorship-2025-2026.

Charts:
  1. Multi-signal timeline: OONI monthly anomaly rate (bars) + CF Radar monthly avg (line)
  2. Cloudflare Radar weekly (Aug 2025 – Apr 2026), election phases + routing shift marked
  3. Average blocking rate by category (horizontal bars)

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

OUTPUT_PDF   = REPO_ROOT / "public" / "assets" / "election-censorship-snapshot-2025-26.pdf"
OUTPUT_HTML  = REPO_ROOT / "public" / "assets" / "election-censorship-snapshot-2025-26.html"
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
    labels, rates, colors = [], [], []
    election_start = "2025-11"
    phase1 = "2025-12"
    phase2 = "2026-01"
    for row in monthly:
        m = row.get("month") or row.get("period", "")[:7]
        if not m:
            continue
        rate = row.get("anomaly_rate", 0)
        labels.append(m)
        rates.append(rate)
        if m < election_start:
            colors.append("rgba(148,163,184,0.45)")
        elif m == election_start:
            colors.append("rgba(251,191,36,0.8)")
        elif m in (phase1, phase2):
            colors.append("rgba(239,68,68,0.85)")
        else:
            colors.append("rgba(148,163,184,0.35)")
    return labels, rates, colors


def cf_monthly_averages(cf_weekly, ooni_labels):
    """Aggregate CF weekly values to monthly averages matching ooni_labels."""
    from collections import defaultdict
    monthly = defaultdict(list)
    for row in cf_weekly:
        ts = row.get("timestamp", "")[:7]  # YYYY-MM
        val = row.get("cf_traffic")
        if ts and val is not None:
            monthly[ts].append(val)
    avgs = []
    for m in ooni_labels:
        vals = monthly.get(m, [])
        avgs.append(round(sum(vals) / len(vals), 1) if vals else None)
    return avgs


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
            colors.append("rgba(251,191,36,0.75)")
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
    cf_monthly_avg                = cf_monthly_averages(cf_weekly, o_labels)
    cf_labels, cf_vals, cf_colors = cf_chart_data(cf_weekly)
    b_labels, b_avgs, b_colors    = blocked_chart_data(blocked_sites)

    dataset_version = metrics.get("dataset_version", "v2026.04.26")
    generated_at    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_events    = metrics.get("total_shutdown_events", 95)
    impact_days     = metrics.get("shutdown_impact_days_total", 0)
    blocked_count   = metrics.get("confirmed_blocked_sites", 42)

    o_labels_json      = json.dumps(o_labels)
    o_rates_json       = json.dumps(o_rates)
    o_colors_json      = json.dumps(o_colors)
    cf_monthly_json    = json.dumps(cf_monthly_avg)
    cf_labels_json     = json.dumps(cf_labels)
    cf_vals_json       = json.dumps(cf_vals)
    cf_colors_json     = json.dumps(cf_colors)
    b_labels_json      = json.dumps(b_labels)
    b_avgs_json        = json.dumps(b_avgs)
    b_colors_json      = json.dumps(b_colors)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Myanmar Election 2025–2026: Censorship Snapshot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Helvetica Neue', Arial, 'Liberation Sans', sans-serif;
    background: #fff;
    color: #1e293b;
    width: 210mm;
    min-height: 297mm;
    padding: 12mm 15mm 10mm;
  }}

  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 3px solid #00D4C8;
    padding-bottom: 9px;
    margin-bottom: 11px;
  }}
  .header-left h1 {{
    font-size: 19px;
    font-weight: 700;
    color: #0A1628;
    line-height: 1.2;
  }}
  .header-left .subtitle {{
    font-size: 10.5px;
    color: #64748b;
    margin-top: 3px;
  }}
  .header-right {{
    text-align: right;
    font-size: 9.5px;
    color: #94a3b8;
    line-height: 1.7;
  }}
  .header-right .logo {{
    font-size: 11px;
    font-weight: 700;
    color: #0A1628;
  }}

  .findings {{
    display: flex;
    gap: 7px;
    margin-bottom: 11px;
  }}
  .finding-card {{
    flex: 1;
    background: #f8fafc;
    border-left: 3px solid #00D4C8;
    padding: 6px 9px;
    border-radius: 0 4px 4px 0;
  }}
  .finding-card .value {{
    font-size: 21px;
    font-weight: 700;
    color: #0A1628;
    line-height: 1;
  }}
  .finding-card .label {{
    font-size: 9px;
    color: #64748b;
    margin-top: 2px;
    line-height: 1.35;
  }}
  .finding-card.alert .value {{ color: #ef4444; }}
  .finding-card.warn  .value {{ color: #f59e0b; }}
  .finding-card.teal  .value {{ color: #0d9488; }}

  .charts-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 11px;
  }}
  .chart-box {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    padding: 9px 11px;
  }}
  .chart-box.full-width {{
    grid-column: 1 / -1;
  }}
  .chart-box h3 {{
    font-size: 10.5px;
    font-weight: 600;
    color: #0A1628;
    margin-bottom: 2px;
  }}
  .chart-note {{
    font-size: 8.5px;
    color: #64748b;
    margin-bottom: 5px;
  }}
  canvas {{
    max-height: 140px;
  }}
  .chart-box.full-width canvas {{
    max-height: 120px;
  }}

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
    font-size: 8px;
    color: #475569;
  }}
  .legend-dot {{
    width: 8px; height: 8px;
    border-radius: 2px;
    flex-shrink: 0;
  }}
  .legend-line {{
    width: 14px; height: 3px;
    border-radius: 2px;
    flex-shrink: 0;
  }}

  /* Analysis section */
  .analysis {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
    padding: 10px 14px;
    margin-bottom: 10px;
  }}
  .analysis h3 {{
    font-size: 11px;
    font-weight: 700;
    color: #0A1628;
    margin-bottom: 7px;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }}
  .analysis-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 16px;
  }}
  .finding {{
    display: flex;
    gap: 6px;
    align-items: flex-start;
  }}
  .finding-icon {{
    flex-shrink: 0;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 8px;
    font-weight: 700;
    color: #fff;
    margin-top: 1px;
  }}
  .finding-icon.red   {{ background: #ef4444; }}
  .finding-icon.amber {{ background: #f59e0b; }}
  .finding-icon.teal  {{ background: #0d9488; }}
  .finding-icon.purple {{ background: #7c3aed; }}
  .finding p {{
    font-size: 9px;
    line-height: 1.5;
    color: #334155;
  }}
  .finding strong {{ color: #0A1628; font-weight: 600; }}

  .downloads {{
    background: #f0fdfa;
    border: 1px solid #99f6e4;
    border-radius: 5px;
    padding: 8px 12px;
    margin-bottom: 9px;
  }}
  .downloads h3 {{
    font-size: 10px;
    font-weight: 600;
    color: #0A1628;
    margin-bottom: 6px;
  }}
  .download-links {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .dl-link {{
    background: #fff;
    border: 1px solid #5eead4;
    border-radius: 3px;
    padding: 3px 8px;
    font-size: 9px;
    font-family: 'Courier New', 'Liberation Mono', monospace;
    color: #0f766e;
    text-decoration: none;
    font-weight: 500;
  }}

  .footer {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-top: 1px solid #e2e8f0;
    padding-top: 7px;
    font-size: 8px;
    color: #94a3b8;
    line-height: 1.6;
  }}
  .footer a {{ color: #0d9488; text-decoration: none; }}
  .footer strong {{ color: #475569; }}

  @media print {{
    body {{ padding: 8mm 12mm; }}
  }}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="header-left">
    <h1>Myanmar Election 2025&#8211;2026: Censorship Snapshot</h1>
    <div class="subtitle">Independent technical monitoring &#8212; OONI &#183; Cloudflare Radar &#183; BGP &#183; KeepItOn / Access Now</div>
  </div>
  <div class="header-right">
    <div class="logo">internetinmyanmar.com</div>
    <div>Observatory &#183; {generated_at}</div>
    <div>Dataset {dataset_version}</div>
  </div>
</div>

<!-- Key metrics -->
<div class="findings">
  <div class="finding-card alert">
    <div class="value">18.6%</div>
    <div class="label">OONI anomaly rate Dec 2025<br>(below Nov&#8217;s 23.2% &#8212; no spike)</div>
  </div>
  <div class="finding-card warn">
    <div class="value">{total_events}</div>
    <div class="label">Access Now&#8211;verified shutdowns<br>in Myanmar 2025 (KeepItOn)</div>
  </div>
  <div class="finding-card alert">
    <div class="value">89%</div>
    <div class="label">Facebook OONI anomaly rate<br>during election period</div>
  </div>
  <div class="finding-card teal">
    <div class="value">{blocked_count}</div>
    <div class="label">Domains tracked &#8212; avg 77%<br>blocked across all categories</div>
  </div>
</div>

<!-- Charts -->
<div class="charts-grid">

  <!-- Chart 1: Multi-signal OONI + CF Radar overlay (full width) -->
  <div class="chart-box full-width">
    <h3>Signal 1 + Signal 2 &#8212; OONI Anomaly Rate (bars) &#183; Cloudflare Radar Monthly Avg (line)</h3>
    <div class="chart-note">Two independent data sources on one timeline. Bars: share of OONI measurements returning anomalous results (left axis). Line: CF Radar traffic index monthly average (right axis). No spike on election days confirms ambient censorship model.</div>
    <canvas id="chart-combined"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:rgba(148,163,184,0.45)"></div>Baseline OONI rate</div>
      <div class="legend-item"><div class="legend-dot" style="background:rgba(251,191,36,0.8)"></div>Campaign period (Nov 2025)</div>
      <div class="legend-item"><div class="legend-dot" style="background:rgba(239,68,68,0.85)"></div>Voting phases (Dec 2025 &#8211; Jan 2026)</div>
      <div class="legend-item"><div class="legend-line" style="background:#0d9488"></div>CF Radar monthly avg (right axis)</div>
    </div>
  </div>

  <!-- Chart 2: CF Radar weekly -->
  <div class="chart-box">
    <h3>Cloudflare Radar Weekly &#8212; Aug 2025&#8211;Apr 2026</h3>
    <div class="chart-note">Amber: election period. Red: post-election routing shift (Feb 2026+) consistent with Great Firewall-style infrastructure activation.</div>
    <canvas id="chart-cf"></canvas>
  </div>

  <!-- Chart 3: Blocking by category -->
  <div class="chart-box">
    <h3>Average OONI Blocking Rate by Category</h3>
    <div class="chart-note">Mean anomaly rate across {len(blocked_sites)} tracked domains (OONI Web Connectivity, Apr 2026).</div>
    <canvas id="chart-blocked"></canvas>
  </div>

</div>

<!-- Analysis -->
<div class="analysis">
  <h3>Key Findings &#8212; Context and Analysis</h3>
  <div class="analysis-grid">
    <div class="finding">
      <div class="finding-icon red">1</div>
      <p><strong>No election-day spike &#8212; the absence is the finding.</strong> OONI anomaly rates in December 2025 (18.6%) were <em>lower</em> than November (23.2%). The junta staged an election inside a pre-censored information environment and required no additional emergency action.</p>
    </div>
    <div class="finding">
      <div class="finding-icon amber">2</div>
      <p><strong>Ambient censorship replaced acute shutdown.</strong> Facebook (89% blocked), independent media (66&#8211;81%), and VPN services (69&#8211;87%) were inaccessible throughout the election period. With {total_events} verified shutdown events in 2025 and 131+ townships under full blackout, Myanmar voters had no access to independent information.</p>
    </div>
    <div class="finding">
      <div class="finding-icon teal">3</div>
      <p><strong>Post-election routing shift signals infrastructure change.</strong> Cloudflare Radar traffic jumped from 37% (Jan 2026) to 69&#8239;&#8594;&#8239;84&#8239;&#8594;&#8239;93% in February 2026 &#8212; a sustained structural change consistent with the activation of a centralised national firewall linked to the Geedge Networks&#8211;China collaboration exposed in September 2025.</p>
    </div>
    <div class="finding">
      <div class="finding-icon purple">4</div>
      <p><strong>Two independent signals, one consistent picture.</strong> OONI application-layer measurements and Cloudflare Radar network-layer data independently confirm the same trajectory: steady chronic censorship through the election, then a qualitative escalation post-February 2026. BGP routing data (active from April 2026) now monitors 130+ Myanmar ASNs in real time.</p>
    </div>
  </div>
</div>

<!-- Downloads -->
<div class="downloads">
  <h3>Download the underlying datasets (CC BY 4.0 &#183; internetinmyanmar.com)</h3>
  <div class="download-links">
    <a class="dl-link" href="https://internetinmyanmar.com/data/ooni_timeseries.csv">ooni_timeseries.csv</a>
    <a class="dl-link" href="https://internetinmyanmar.com/data/keepiton_shutdowns.csv">keepiton_shutdowns.csv</a>
    <a class="dl-link" href="https://internetinmyanmar.com/data/bgp_events.csv">bgp_events.csv</a>
    <a class="dl-link" href="https://internetinmyanmar.com/data/unified_events.json">unified_events.json</a>
  </div>
</div>

<!-- Footer -->
<div class="footer">
  <div>
    OONI data CC BY 4.0 &#183; Cloudflare Radar CC BY&#8211;NC 4.0 &#183; KeepItOn / Access Now<br>
    Cite as: <em>Internet in Myanmar Observatory, internetinmyanmar.com, {generated_at}</em><br>
    Contact: <strong>admin@internetinmyanmar.com</strong>
  </div>
  <div style="text-align:right">
    Full article + interactive charts:<br>
    <a href="https://internetinmyanmar.com/articles/myanmar-election-internet-censorship-2025-2026/">internetinmyanmar.com/articles/myanmar-election&#8230;</a>
  </div>
</div>

<script>
const ooniLabels   = {o_labels_json};
const ooniRates    = {o_rates_json};
const ooniColors   = {o_colors_json};
const cfMonthly    = {cf_monthly_json};
const cfLabels     = {cf_labels_json};
const cfVals       = {cf_vals_json};
const cfColors     = {cf_colors_json};
const bLabels      = {b_labels_json};
const bAvgs        = {b_avgs_json};
const bColors      = {b_colors_json};

Chart.defaults.font = {{ family: "'Helvetica Neue', Arial, sans-serif", size: 8.5 }};
Chart.defaults.color = '#475569';

// Chart 1 — Combined OONI bars + CF Radar line
new Chart(document.getElementById('chart-combined'), {{
  data: {{
    labels: ooniLabels,
    datasets: [
      {{
        type: 'bar',
        label: 'OONI Anomaly Rate (%)',
        data: ooniRates,
        backgroundColor: ooniColors,
        borderRadius: 2,
        borderSkipped: false,
        yAxisID: 'y',
        order: 2,
      }},
      {{
        type: 'line',
        label: 'CF Radar Monthly Avg (%)',
        data: cfMonthly,
        borderColor: '#0d9488',
        borderWidth: 2.5,
        pointBackgroundColor: '#0d9488',
        pointRadius: 3,
        pointHoverRadius: 5,
        fill: false,
        tension: 0.35,
        yAxisID: 'y2',
        order: 1,
        spanGaps: true,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y}}%`
        }}
      }}
    }},
    scales: {{
      x: {{
        ticks: {{ maxTicksLimit: 14, maxRotation: 45, font: {{ size: 7 }} }},
        grid: {{ display: false }}
      }},
      y: {{
        min: 0, max: 42,
        position: 'left',
        title: {{ display: true, text: 'OONI %', font: {{ size: 7.5 }}, color: '#94a3b8' }},
        ticks: {{ callback: v => v + '%', stepSize: 10, font: {{ size: 7.5 }} }},
        grid: {{ color: 'rgba(0,0,0,0.04)' }}
      }},
      y2: {{
        min: 0, max: 110,
        position: 'right',
        title: {{ display: true, text: 'CF Radar %', font: {{ size: 7.5 }}, color: '#0d9488' }},
        ticks: {{ callback: v => v + '%', stepSize: 25, font: {{ size: 7.5 }}, color: '#0d9488' }},
        grid: {{ display: false }}
      }}
    }}
  }}
}});

// Chart 2 — CF Radar weekly
const cfShort = cfLabels.map(l => l.slice(5));
new Chart(document.getElementById('chart-cf'), {{
  type: 'line',
  data: {{
    labels: cfShort,
    datasets: [{{
      data: cfVals,
      borderColor: '#0d9488',
      borderWidth: 2,
      pointBackgroundColor: cfColors,
      pointBorderColor: cfColors,
      pointRadius: 3,
      fill: true,
      backgroundColor: 'rgba(13,148,136,0.07)',
      tension: 0.3,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.y}}%` }} }}
    }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 10, maxRotation: 45, font: {{ size: 7 }} }}, grid: {{ display: false }} }},
      y: {{
        min: 0, max: 110,
        ticks: {{ callback: v => v + '%', stepSize: 25, font: {{ size: 7.5 }} }},
        grid: {{ color: 'rgba(0,0,0,0.04)' }}
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
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.x}}% avg anomaly` }} }}
    }},
    scales: {{
      x: {{
        min: 0, max: 100,
        ticks: {{ callback: v => v + '%', font: {{ size: 7.5 }} }},
        grid: {{ color: 'rgba(0,0,0,0.04)' }}
      }},
      y: {{ ticks: {{ font: {{ size: 8.5 }} }}, grid: {{ display: false }} }}
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
