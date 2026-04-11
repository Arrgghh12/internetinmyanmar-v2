/**
 * Normalizes a digest collection entry into the shape ArticleList expects.
 * Digest entries link to /digest/[slug] and carry a source badge.
 */
export function digestToArticle(entry: {
  slug: string
  data: {
    title: string
    source: string
    publishedAt: Date
    tags: string[]
    category: string
    sourceScore?: number
  }
}) {
  return {
    slug: entry.slug,
    href: `/digest/${entry.slug}/`,
    data: {
      title: entry.data.title,
      excerpt: `Via ${entry.data.source} — curated digest entry.`,
      publishedAt: entry.data.publishedAt,
      author: entry.data.source,
      tags: entry.data.tags,
      digestSource: entry.data.source,
      digestCategory: entry.data.category,
    },
  }
}
