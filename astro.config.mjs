// @ts-check
import { defineConfig } from 'astro/config'
import mdx from '@astrojs/mdx'
import sitemap from '@astrojs/sitemap'
import tailwindcss from '@tailwindcss/vite'
import robotsTxt from 'astro-robots-txt'
import keystatic from '@keystatic/astro'
import cloudflare from '@astrojs/cloudflare'

export default defineConfig({
  site: 'https://www.internetinmyanmar.com',
  output: 'server',
  adapter: cloudflare(),

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'fr', 'es', 'it', 'my'],
    routing: {
      prefixDefaultLocale: false,
    },
  },

  integrations: [
    mdx(),
    sitemap({
      i18n: {
        defaultLocale: 'en',
        locales: {
          en: 'en-US',
          fr: 'fr-FR',
          es: 'es-ES',
          it: 'it-IT',
        },
      },
    }),
    robotsTxt(),
    keystatic(),
  ],

  vite: {
    plugins: [tailwindcss()],
  },
})
