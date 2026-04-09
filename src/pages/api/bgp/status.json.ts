import type { APIRoute } from 'astro'
import asnStatus from '../../../data/asn-status.json'
import metadata  from '../../../data/asn-metadata.json'

export const prerender = false

export const GET: APIRoute = () => {
  const status  = asnStatus  as Record<string, any>
  const meta    = metadata   as Record<string, any>

  const rows = Object.entries(status).map(([asn, s]) => {
    const m = meta[asn] ?? {}
    return {
      asn,
      as_name:     s.name   ?? null,
      description: m.description ?? s.name ?? null,
      type:        m.type   ?? 'ISP',
      is_mno:      m.is_mno ?? false,
      is_igw:      m.is_igw ?? false,
      status:      s.status ?? null,
      visibility_pct: s.visibility_pct ?? null,
      status_since:   s.status_since   ?? null,
    }
  })

  return new Response(JSON.stringify(rows, null, 2), {
    headers: {
      'Content-Type':                'application/json',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control':               'public, max-age=300',
    },
  })
}
