import type { APIRoute } from 'astro'
import asnStatus from '../../../data/asn-status.json'
import metadata  from '../../../data/asn-metadata.json'

export const prerender = false

function csvEscape(v: any): string {
  const s = v == null ? '' : String(v)
  if (s.includes(',') || s.includes('"') || s.includes('\n'))
    return `"${s.replace(/"/g, '""')}"`
  return s
}

export const GET: APIRoute = () => {
  const status = asnStatus as Record<string, any>
  const meta   = metadata  as Record<string, any>

  const headers = ['asn','description','as_name','type','is_mno','is_igw','status','visibility_pct','status_since']
  const rows    = Object.entries(status).map(([asn, s]) => {
    const m = meta[asn] ?? {}
    return [
      asn,
      m.description ?? s.name ?? '',
      s.name ?? '',
      m.type ?? 'ISP',
      m.is_mno ?? false,
      m.is_igw ?? false,
      s.status ?? '',
      s.visibility_pct ?? '',
      s.status_since   ?? '',
    ].map(csvEscape).join(',')
  })

  const csv = [headers.join(','), ...rows].join('\r\n')
  const filename = `myanmar-bgp-${new Date().toISOString().slice(0,10)}.csv`

  return new Response(csv, {
    headers: {
      'Content-Type':        'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Cache-Control':       'public, max-age=300',
    },
  })
}
