import { defineCollection, z } from 'astro:content'

const articles = defineCollection({
  type: 'content',
  schema: z.object({
    title:            z.string(),
    seoTitle:         z.string().max(60),
    metaDescription:  z.string().max(155),
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
    lang:             z.enum(['en', 'fr', 'es', 'it', 'my']).default('en'),
    translationOf:    z.string().optional(),
    sources:          z.array(z.string().url()).optional(),
    migrated:         z.boolean().default(false),
    originalUrl:      z.string().url().optional(),
    archived:         z.boolean().default(false),
    archivedAt:       z.string().optional(),
    archivedReason:   z.string().optional(),
    restoredAt:       z.string().optional(),
  }),
})

const observatory = defineCollection({
  type: 'data',
  schema: z.object({
    lastUpdated:             z.string(),
    activeShutdowns:         z.number(),
    blockedSites:            z.number(),
    daysSinceLastMajorOutage: z.number(),
    note:                    z.string().optional(),
  }),
})

export const collections = { articles, observatory }
