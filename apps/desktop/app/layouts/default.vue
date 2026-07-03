<script setup lang="ts">
// Contab shell — the Dandelyon · Órbita (Contabilidad) consumer of the design system.
// Sidebar lockup + nav, ⌘K in the topbar, theme toggle, user at the foot. La campana de
// notificaciones mock y el beacon de estado ficticio se retiraron (0.1.4 #7) hasta que exista
// una fuente real. Playground-only pieces (Control de marca panel, resizable grid, resolution
// letterbox, Helm/Timón spines) are intentionally absent.
import { Sun, Moon, Home, Building2, FileSearch, LifeBuoy, HelpCircle, Bell, ChevronDown } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover'
import { Button } from '~/components/ui/button'
import { useTour } from '~/composables/useTour'
import { TOURS } from '~/lib/tours'

const route = useRoute()
const pg = useBrand()
// Theme/preferences live in usePrefs() (single source of truth, issue #2). Calling it here also
// initialises the singleton early so prefs apply before the SidebarUser panel mounts.
const prefs = usePrefs()
const isDark = computed(() =>
  prefs.prefs.theme === 'dark'
  || (prefs.prefs.theme === 'system' && import.meta.client && window.matchMedia('(prefers-color-scheme: dark)').matches),
)
function toggleTheme() { prefs.setPref('theme', isDark.value ? 'light' : 'dark') }

type NavLeaf = { label: string; to: string; match?: (p: string) => boolean }
type NavItem = NavLeaf | { label: string; icon: unknown; children: NavLeaf[] }

// Real Contab nav. Empresas owns the company sub-routes (detail + carga); Consulta DIAN is its
// own area. `{ label, to, icon }` (+ optional children for groups) — flattened for ⌘K + crumb.
const nav: (NavLeaf & { icon: unknown })[] = [
  { label: 'Inicio', to: '/', icon: Home, match: p => p === '/' },
  { label: 'Empresas', to: '/empresas', icon: Building2, match: p => p === '/empresas' || p === '/empresa' || p === '/load' },
  { label: 'Consulta DIAN', to: '/consulta-dian', icon: FileSearch },
  { label: 'Ayuda', to: '/ayuda', icon: LifeBuoy },
]
const flatNav = computed<NavLeaf[]>(() => nav.map(n => ({ label: n.label, to: n.to, match: n.match })))

const leafActive = (n: NavLeaf) => (n.match ? n.match(route.path) : route.path === n.to)
const crumbLeaf = computed(() => flatNav.value.find(leafActive)?.label ?? 'Contab')

// Tutoriales interactivos: el botón "?" del topbar lanza el tour de la vista actual; al llegar
// desde el hub de Ayuda con ?tour=1, se arranca solo (y se limpia el parámetro).
const tour = useTour()
const currentTour = computed(() => TOURS[route.path])
function startTour() { if (currentTour.value) tour.start(currentTour.value.steps, currentTour.value.id) }
watch(() => route.query.tour, (v) => {
  if (!v) return
  const t = TOURS[route.path]
  if (t) setTimeout(() => tour.start(t.steps, t.id), 350)
  const { tour: _omit, ...rest } = route.query
  navigateTo({ path: route.path, query: rest }, { replace: true })
}, { immediate: true })
</script>

<template>
  <SidebarProvider>
    <Sidebar collapsible="icon" data-pg-sidebar>
      <!-- collapsed rail: drop padding + center the mark; expanded: pad + left-align -->
      <SidebarHeader class="min-h-16 items-center justify-center px-0 py-2 group-data-[state=expanded]:items-start group-data-[state=expanded]:px-3">
        <SidebarLogo />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>General</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem v-for="item in nav" :key="item.to">
                <SidebarMenuButton as-child :is-active="leafActive(item)" :tooltip="item.label">
                  <NuxtLink :to="item.to">
                    <component :is="item.icon" />
                    <span class="truncate group-data-[collapsible=icon]:hidden">{{ item.label }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <!-- user / session block at the foot of the sidebar (userPlacement = bottom) -->
        <div class="mt-auto p-2">
          <SidebarUser />
        </div>
      </SidebarContent>

      <SidebarFooter class="gap-0 border-t border-sidebar-border p-0">
        <!-- decorative cosmos scene (needs a positioned, sized parent) -->
        <div class="relative h-24 overflow-hidden">
          <SidebarCosmos />
        </div>
        <!-- maker credit ribbon — required in every Dandelyon app (BRAND.md §10) -->
        <div class="border-t border-sidebar-border p-2">
          <MakerCredit />
        </div>
      </SidebarFooter>
    </Sidebar>

    <SidebarInset class="flex h-svh flex-col overflow-hidden">
      <!-- topbar -->
      <header data-pg-topbar class="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
        <SidebarTrigger />
        <span class="h-5 w-px shrink-0 bg-border" />
        <nav aria-label="Breadcrumb" class="text-sm">
          <ol class="flex items-center gap-1.5">
            <li class="flex items-center gap-1.5">
              <span class="whitespace-nowrap font-heading text-muted-foreground">Dandelyon · {{ pg.subName }}</span>
              <span class="text-muted-foreground">/</span>
            </li>
            <li>
              <Popover>
                <PopoverTrigger class="inline-flex items-center gap-1 font-semibold text-foreground transition-colors hover:text-foreground">
                  {{ crumbLeaf }}
                  <ChevronDown class="size-3.5 text-muted-foreground" />
                </PopoverTrigger>
                <PopoverContent align="start" :side-offset="6" class="w-56 p-1.5">
                  <NuxtLink v-for="item in flatNav" :key="item.to" :to="item.to"
                    class="block rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent"
                    :class="leafActive(item) ? 'font-semibold text-foreground' : 'text-muted-foreground'">
                    {{ item.label }}
                  </NuxtLink>
                </PopoverContent>
              </Popover>
            </li>
          </ol>
        </nav>

        <!-- ⌘K command palette (solar-rail spine → folds into the topbar) -->
        <div class="mx-auto hidden w-full max-w-sm md:block">
          <CommandFirst :nav="flatNav" />
        </div>

        <div class="ml-auto flex items-center gap-3">
          <!-- notificaciones (sin badge ni datos ficticios; se poblará cuando haya una fuente real) -->
          <Popover>
            <PopoverTrigger aria-label="Notificaciones"
              class="inline-flex size-9 items-center justify-center rounded-full border border-border bg-muted text-foreground transition-colors hover:bg-accent">
              <Bell class="size-[18px]" />
            </PopoverTrigger>
            <PopoverContent align="end" :side-offset="8" class="w-72 p-0">
              <div class="border-b border-border px-3 py-2 text-sm font-medium">Notificaciones</div>
              <div class="px-3 py-6 text-center text-sm text-muted-foreground">No tienes notificaciones.</div>
            </PopoverContent>
          </Popover>

          <!-- tutorial de la vista actual -->
          <Button v-if="currentTour" variant="outline" size="icon" aria-label="Ver tutorial de esta pantalla"
            title="Ver tutorial de esta pantalla" class="rounded-full bg-muted text-foreground" @click="startTour">
            <HelpCircle class="size-[18px]" />
          </Button>
          <!-- theme toggle (claro / oscuro) — vía usePrefs (fuente única; el panel de preferencias coincide) -->
          <Button variant="outline" size="icon" aria-label="Cambiar tema"
            class="rounded-full bg-muted text-foreground" @click="toggleTheme()">
            <Moon v-if="!isDark" class="size-[18px]" />
            <Sun v-else class="size-[18px]" />
          </Button>
        </div>
      </header>

      <!-- content -->
      <div class="min-h-0 flex-1 overflow-hidden">
        <div data-pg-content class="h-full min-w-0 overflow-y-auto">
          <slot />
        </div>
      </div>
    </SidebarInset>
    <ToastContainer />
    <TourGuide />
  </SidebarProvider>
</template>
