export interface OutageEvent {
  asn: string
  name: string
  started_at: string
  duration_minutes: number | null
  resolved: boolean
}

export interface ChartWindow {
  labels: string[]
  data: number[]
  granularity: string
  total: number
}

const FLAP_THRESHOLD = 5  // minutes — below this is likely route flapping

function formatLabel(date: Date, totalDays: number): string {
  if (totalDays === 365)
    return date.toLocaleDateString('en-GB', { month: 'short' })
  if (totalDays >= 30)
    return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' })
}

function groupByPeriod(
  outages: OutageEvent[],
  days: number,
  barsTarget: number,
  significantOnly: boolean,
): ChartWindow {
  const now   = new Date()
  const start = new Date(now.getTime() - days * 86400000)
  const items = outages.filter(o => {
    if (new Date(o.started_at) < start) return false
    if (significantOnly && o.duration_minutes !== null && o.duration_minutes < FLAP_THRESHOLD) return false
    return true
  })

  const msPerBar = (days * 86400000) / barsTarget
  const bars: { label: string; count: number }[] = []

  for (let i = 0; i < barsTarget; i++) {
    const barStart = new Date(start.getTime() + i * msPerBar)
    const barEnd   = new Date(start.getTime() + (i + 1) * msPerBar)
    const count    = items.filter(o => {
      const t = new Date(o.started_at)
      return t >= barStart && t < barEnd
    }).length
    bars.push({ label: formatLabel(barStart, days), count })
  }

  const granularity =
    days === 365 ? 'month' :
    days === 90  ? 'week'  :
    days === 30  ? '3 days' : 'day'

  return {
    labels:      bars.map(b => b.label),
    data:        bars.map(b => b.count),
    granularity,
    total:       items.length,
  }
}

export function buildChartData(outages: OutageEvent[]) {
  return {
    all: {
      '12m': groupByPeriod(outages, 365, 12, false),
      '3m':  groupByPeriod(outages, 90,  13, false),
      '1m':  groupByPeriod(outages, 30,  10, false),
      '1w':  groupByPeriod(outages, 7,   7,  false),
    },
    significant: {
      '12m': groupByPeriod(outages, 365, 12, true),
      '3m':  groupByPeriod(outages, 90,  13, true),
      '1m':  groupByPeriod(outages, 30,  10, true),
      '1w':  groupByPeriod(outages, 7,   7,  true),
    },
  }
}
