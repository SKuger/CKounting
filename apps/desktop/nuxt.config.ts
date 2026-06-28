import tailwindcss from '@tailwindcss/vite'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2026-05-01',
  // SPA. SSR adds no value for a desktop shell and triggers an in-sidebar hydration/context
  // bug where server-rendered nav links wouldn't navigate (teleported popovers did). Matches
  // the Dandelyon playground (ssr:false). Nitro server routes (server/api/*) keep working.
  ssr: false,
  devtools: { enabled: true },
  modules: ['@pinia/nuxt', 'shadcn-nuxt', '@nuxt/fonts'],
  css: ['~/assets/css/main.css'],
  vite: {
    plugins: [tailwindcss()],
    // Pre-bundle these so Vite doesn't discover them at runtime and force full-page reloads
    // (the dep-discovery churn that makes nav look like it "re-renders the whole page").
    optimizeDeps: {
      include: ['reka-ui', 'lucide-vue-next', '@lucide/vue', '@vueuse/core', 'class-variance-authority', 'clsx', 'tailwind-merge', '@tanstack/vue-table'],
    },
  },
  shadcn: { prefix: '', componentDir: './app/components/ui' },
  fonts: {
    families: [
      { name: 'Fraunces',      weights: [400, 500],      provider: 'google' },
      { name: 'Inter',         weights: [400, 500, 600], provider: 'google' },
      { name: 'IBM Plex Mono', weights: [400, 500],      provider: 'google', global: true },
    ],
  },
  app: {
    head: {
      title: 'Contab',
      // Baked Órbita look (consume-plan §5): the sub-brand theme class + the data-* skins
      // (solar rail spine, faro concept, radio Definido, densidad Media, acento Sutil, cosmos
      // Alto/acento, beacon ok, Fraunces + beam). The FOUC script toggles .dark alongside.
      htmlAttrs: {
        'lang': 'es',
        'class': 'theme-orbita',
        'data-concept': 'faro',
        'data-spine': 'beacon',
        'data-strength': 'definido',
        'data-density': 'media',
        'data-accent-spread': 'sutil',
        'data-swell': 'alto',
        'data-ocean-tint': 'accent',
        'data-status': 'ok',
        'data-fraunces': 'on',
        'data-beam': 'on',
      },
      // Browser tab: the Dandelyon mark (RFC 0008 — favicon = brand mark). SVG first, PNG
      // fallbacks. ?v bump = cache-bust (Chrome caches favicons by URL across hard-reload).
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg?v=1' },
        { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32.png?v=1' },
        { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/favicon-16.png?v=1' },
      ],
      // FOUC guard: paint .dark before hydration so there's no flash. Own localStorage key.
      script: [{
        innerHTML:
          "(function(){var t=localStorage.getItem('contab-theme');var d=t==='dark'||(t!=='light'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d)})()",
        tagPosition: 'head',
      }],
    },
  },
  typescript: {
    tsConfig: {
      compilerOptions: {
        paths: {
          'reka-ui': ['./node_modules/reka-ui/dist/index.d.ts'],
        },
      },
    },
  },
})
