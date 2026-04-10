import type { OutageEvent } from './chart-data'
import type { NetworkType, AsnMeta } from './asn-utils'

const FLAP_THRESHOLD = 5

export interface LeaderboardEntry {
  rank: number
  asn: string
  name: string
  type: NetworkType
  outage_count: number
  total_downtime_minutes: number
  longest_outage_minutes: number
  last_outage: string
}

export function computeLeaderboard(
  outages: OutageEvent[],
  metadata: Record<string, AsnMeta>,
  days: number,
  significantOnly: boolean,
  topN = 10,
): LeaderboardEntry[] {
  const cutoff = new Date(Date.now() - days * 86400000)

  const filtered = outages.filter(o => {
    if (new Date(o.started_at) < cutoff) return false
    if (significantOnly && o.duration_minutes !== null && o.duration_minutes < FLAP_THRESHOLD) return false
    return true
  })

  const byAsn: Record<string, OutageEvent[]> = {}
  for (const o of filtered) {
    if (!byAsn[o.asn]) byAsn[o.asn] = []
    byAsn[o.asn].push(o)
  }

  const nowMs = Date.now()

  const entries: LeaderboardEntry[] = Object.entries(byAsn).map(([asn, events]) => {
    const durations = events.map(e => {
      if (e.duration_minutes !== null) return e.duration_minutes as number
      // Ongoing outage — estimate using current time
      return Math.round((nowMs - new Date(e.started_at).getTime()) / 60000)
    })

    return {
      rank:                   0,
      asn,
      name:                   events[0]?.name ?? asn,
      type:                   metadata[asn]?.type ?? 'ISP',
      outage_count:           events.length,
      total_downtime_minutes: durations.reduce((a, b) => a + b, 0),
      longest_outage_minutes: durations.length ? Math.max(...durations) : 0,
      last_outage:            events.at(-1)?.started_at ?? '',
    }
  })

  entries.sort((a, b) =>
    b.outage_count - a.outage_count ||
    b.total_downtime_minutes - a.total_downtime_minutes
  )

  return entries.slice(0, topN).map((e, i) => ({ ...e, rank: i + 1 }))
}

export function buildLeaderboards(
  outages: OutageEvent[],
  metadata: Record<string, AsnMeta>,
) {
  return {
    all: {
      '7d':  computeLeaderboard(outages, metadata, 7,  false),
      '30d': computeLeaderboard(outages, metadata, 30, false),
      '90d': computeLeaderboard(outages, metadata, 90, false),
    },
    significant: {
      '7d':  computeLeaderboard(outages, metadata, 7,  true),
      '30d': computeLeaderboard(outages, metadata, 30, true),
      '90d': computeLeaderboard(outages, metadata, 90, true),
    },
  }
}
