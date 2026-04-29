import rss from '@astrojs/rss'
import { getCollection } from 'astro:content'
import type { APIContext } from 'astro'

export async function GET(context: APIContext) {
  const articles = await getCollection('articles', ({ data }) =>
    !data.draft && !data.unlisted && data.lang === 'en'
  )
  articles.sort((a, b) => b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf())

  return rss({
    title: 'Internet in Myanmar',
    description: 'Independent tracking of internet shutdowns, censorship, and connectivity in Myanmar.',
    site: context.site!,
    items: articles.map((a) => ({
      title: a.data.title,
      pubDate: a.data.publishedAt,
      description: a.data.excerpt,
      link: `/articles/${a.data.slug}/`,
    })),
  })
}
