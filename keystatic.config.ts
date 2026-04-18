import { config, collection, fields } from '@keystatic/core'

export default config({
  storage: { kind: 'local' },

  collections: {
    articles: collection({
      label: 'Articles',
      slugField: 'slug',
      path: 'src/content/articles/*',
      format: { contentField: 'content' },
      schema: {
        title: fields.text({ label: 'Title', validation: { isRequired: true } }),
        seoTitle: fields.text({
          label: 'SEO Title',
          description: 'Max 60 characters. Primary keyword first.',
          validation: { isRequired: true, length: { max: 60 } },
        }),
        metaDescription: fields.text({
          label: 'Meta Description',
          multiline: true,
          description: 'Max 155 characters.',
          validation: { isRequired: true, length: { max: 155 } },
        }),
        slug: fields.text({ label: 'Slug', validation: { isRequired: true } }),
        category: fields.select({
          label: 'Category',
          options: [
            { label: 'Censorship & Shutdowns',   value: 'Censorship & Shutdowns' },
            { label: 'Telecom & Infrastructure', value: 'Telecom & Infrastructure' },
            { label: 'Digital Economy',          value: 'Digital Economy' },
            { label: 'Guides & Tools',           value: 'Guides & Tools' },
            { label: 'News - Mobile',            value: 'News - Mobile' },
            { label: 'News - Broadband',         value: 'News - Broadband' },
            { label: 'News - Policy',            value: 'News - Policy' },
          ],
          defaultValue: 'Censorship & Shutdowns',
        }),
        tags: fields.array(
          fields.text({ label: 'Tag' }),
          { label: 'Tags', itemLabel: (props) => props.value },
        ),
        author: fields.text({ label: 'Author', defaultValue: 'Anna' }),
        publishedAt: fields.date({ label: 'Published At', validation: { isRequired: true } }),
        updatedAt: fields.date({ label: 'Updated At' }),
        draft: fields.checkbox({ label: 'Draft', defaultValue: true }),
        featuredImage: fields.text({ label: 'Featured Image Path' }),
        featuredImageAlt: fields.text({
          label: 'Featured Image Alt',
          description: 'Max 100 characters. Descriptive, no keyword stuffing.',
          validation: { length: { max: 100 } },
        }),
        excerpt: fields.text({
          label: 'Excerpt',
          multiline: true,
          description: 'Max 300 characters.',
          validation: { isRequired: true, length: { max: 300 } },
        }),
        readingTime: fields.number({ label: 'Reading Time (minutes)' }),
        lang: fields.select({
          label: 'Language',
          options: [
            { label: 'English', value: 'en' },
            { label: 'French',  value: 'fr' },
            { label: 'Spanish', value: 'es' },
            { label: 'Italian', value: 'it' },
          ],
          defaultValue: 'en',
        }),
        translationOf: fields.text({ label: 'Translation Of (English slug)' }),
        sources: fields.array(
          fields.url({ label: 'Source URL' }),
          { label: 'Sources', itemLabel: (props) => props.value ?? 'URL' },
        ),
        migrated: fields.checkbox({ label: 'Migrated from WordPress', defaultValue: false }),
        originalUrl: fields.url({ label: 'Original WordPress URL' }),
        content: fields.mdx({ label: 'Content' }),
      },
    }),
  },
})
