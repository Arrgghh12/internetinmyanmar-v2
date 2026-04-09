import type { APIRoute } from 'astro'
import { getCollection } from 'astro:content'

export const prerender = true

export const GET: APIRoute = async () => {
  const articles = await getCollection('articles', ({ data }) =>
    !data.draft && !data.archived && data.lang === 'en'
  )

  const digest = await getCollection('digest', ({ data }) => !data.draft)

  const index = [
    ...articles.map((a) => ({
      slug: a.slug,
      title: a.data.title,
      excerpt: a.data.excerpt ?? '',
      categories: a.data.categories,
      tags: a.data.tags,
      publishedAt: a.data.publishedAt.toISOString().slice(0, 10),
      type: 'article',
      href: `/articles/${a.slug}/`,
    })),
    ...digest.map((d) => ({
      slug: d.slug,
      title: d.data.title,
      excerpt: '',
      categories: [d.data.category],
      tags: d.data.tags,
      publishedAt: d.data.publishedAt.toISOString().slice(0, 10),
      type: 'digest',
      href: `/digest/${d.slug}/`,
    })),
  ]

  return new Response(JSON.stringify(index), {
    headers: { 'Content-Type': 'application/json' },
  })
}
