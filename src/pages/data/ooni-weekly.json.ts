import data from '../../data/ooni-history-weekly.json'

export const prerender = true

export function GET() {
  return new Response(JSON.stringify(data, null, 2), {
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=3600' },
  })
}
