import { defineCollection, z } from 'astro:content'

const articles = defineCollection({
  type: 'content',
  schema: z.object({
    title:            z.string(),
    seoTitle:         z.string().max(60),
    metaDescription:  z.string().max(155),
    slug:             z.string(),
    category:         z.enum([
      'Censorship & Shutdowns',
      'Telecom & Infrastructure',
      'Digital Economy',
      'Guides & Tools',
      'News - Mobile',
      'News - Broadband',
      'News - Policy',
    ]),
    tags:             z.array(z.string()),
    author:           z.string().default('Anna Faure Revol'),
    publishedAt:      z.coerce.date(),
    updatedAt:        z.coerce.date().optional(),
    draft:            z.boolean().default(true),
    featuredImage:    z.string().optional(),
    featuredImageAlt: z.string().max(100).optional(),
    excerpt:          z.string().max(300),
    readingTime:      z.number().optional(),
    lang:             z.enum(['en', 'fr', 'es', 'it']).default('en'),
    translationOf:    z.string().optional(),
    sources:          z.array(z.string().url()).optional(),
    migrated:         z.boolean().default(false),
    originalUrl:      z.string().url().optional(),
  }),
})

export const collections = { articles }
