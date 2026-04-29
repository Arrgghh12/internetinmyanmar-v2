import { defineCollection, z } from 'astro:content'

const articles = defineCollection({
  type: 'content',
  schema: z.object({
    title:            z.string(),
    seoTitle:         z.string().max(60),
    metaDescription:  z.string().max(155),
    categories:       z.array(z.enum([
      'Censorship & Shutdowns',
      'VPN & Security',
      'ISP & Broadband',
      'Mobile & Data Plans',
      'Telecom & Infrastructure',
      'Digital Services',
      'Policy & Regulation',
    ])).min(1),
    tags:             z.array(z.string()),
    author:           z.string().default('Sacha Nakeo'),
    publishedAt:      z.coerce.date(),
    updatedAt:        z.coerce.date().optional(),
    draft:            z.boolean().default(true),
    unlisted:         z.boolean().default(false),
    featuredImage:    z.string().optional(),
    featuredImageAlt: z.string().max(100).optional(),
    featuredImageCredit: z.string().optional(),
    featuredImageCreditUrl: z.string().url().optional(),
    excerpt:          z.string().max(300),
    readingTime:      z.number().optional(),
    lang:             z.enum(['en', 'fr', 'es', 'it', 'my']).default('en'),
    translationOf:    z.string().optional(),
    sources:          z.array(z.string().url()).optional(),
    migrated:         z.boolean().default(false),
    originalUrl:      z.string().url().optional(),
    faq:              z.array(z.object({ q: z.string(), a: z.string() })).optional(),
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

const digest = defineCollection({
  type: 'content',
  schema: z.object({
    title:       z.string(),
    sourceTitle: z.string(),
    source:      z.string(),
    sourceUrl:   z.string().url(),
    canonical:   z.string().url(),
    publishedAt: z.coerce.date(),
    addedAt:     z.coerce.date(),
    excerpt:     z.string().max(500).optional(),
    category:    z.enum(['Shutdown', 'Censorship', 'Arrest', 'Policy', 'Data', 'Surveillance', 'Other']),
    tags:        z.array(z.string()),
    sourceScore: z.number().min(0).max(100),
    sourceTier:  z.enum(['A', 'B', 'C', 'D']),
    sourceLabel: z.string(),
    type:         z.literal('digest').default('digest'),
    draft:        z.boolean().default(false),
    originalTitle: z.string().optional(),
    sourceLang:    z.string().optional(),
    featuredImage: z.string().url().optional(),
  }),
})

export const collections = { articles, observatory, digest }
