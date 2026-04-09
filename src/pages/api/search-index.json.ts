import type { APIRoute } from 'astro'
import { getCollection } from 'astro:content'

export const prerender = true

export const GET: APIRoute = async () => {
  const articles = await getCollection('articles', ({ data }) =>
    !data.draft && !data.archived && data.lang === 'en'
  )

  const index = articles.map((a) => ({
    slug: a.slug,
    title: a.data.title,
    excerpt: a.data.excerpt ?? '',
    categories: a.data.categories,
    tags: a.data.tags,
    publishedAt: a.data.publishedAt.toISOString().slice(0, 10),
  }))

  return new Response(JSON.stringify(index), {
    headers: { 'Content-Type': 'application/json' },
  })
}
