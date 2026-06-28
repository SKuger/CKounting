<script setup lang="ts">
// User / logged-in block. variant="sidebar" → full block that collapses to the avatar on
// the icon rail (finance-lch / lab-qc / shadcn convention). variant="navbar" → compact
// pill for the topbar-right. Logged-in dot uses the accent-INDEPENDENT status palette.
// Mock persona (playground): a QC coordinator — an early orbiter in the Dandelyon constellation.
import { ChevronsUpDown, LogOut, UserRound, Settings } from 'lucide-vue-next'
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover'
import { useSidebar } from '~/components/ui/sidebar'

const props = withDefaults(defineProps<{ variant?: 'sidebar' | 'navbar' }>(), { variant: 'sidebar' })
const { state } = useSidebar()
const pg = useBrand()
// In the sidebar, align the menu's end to the trigger's end when the block sits at the BOTTOM
// (the menu rises from the user box's bottom edge); top placement keeps the start-aligned menu.
const menuAlign = computed(() => props.variant === 'navbar' || pg.userPlacement === 'bottom' ? 'end' : 'start')
const user = { name: 'Carlos Kuger', role: 'Mejor contador del mundo', email: 'ckuger@hematologico.com', initials: 'CK' }
// in the sidebar, hide the text when collapsed to the icon rail; in the navbar always show
const showText = computed(() => props.variant === 'navbar' || state.value === 'expanded')
</script>

<template>
  <Popover>
    <PopoverTrigger
      :class="[
        'flex items-center gap-2 rounded-md text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring',
        variant === 'navbar'
          ? 'h-9 px-1.5 hover:bg-accent'
          : 'w-full p-1.5 hover:bg-sidebar-accent',
        variant === 'sidebar' && state === 'collapsed' ? 'justify-center' : '',
      ]">
      <span class="relative inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-sidebar-primary font-mono text-xs font-medium text-sidebar-primary-foreground">
        {{ user.initials }}
        <span class="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 bg-status-success"
              :class="variant === 'navbar' ? 'border-card' : 'border-sidebar'" title="Conectada" />
      </span>
      <span v-if="showText" class="min-w-0" :class="variant === 'navbar' ? 'hidden flex-1 lg:block' : 'flex-1'">
        <span class="block truncate text-sm font-medium leading-tight" :class="variant === 'navbar' ? 'text-foreground' : 'text-sidebar-foreground'">{{ user.name }}</span>
        <span class="block truncate text-xs leading-tight text-muted-foreground">{{ user.role }}</span>
      </span>
      <ChevronsUpDown v-if="showText" class="size-4 shrink-0 text-muted-foreground" :class="variant === 'navbar' ? 'hidden lg:block' : ''" />
    </PopoverTrigger>

    <PopoverContent :align="menuAlign" :side="variant === 'navbar' ? 'bottom' : 'right'" :side-offset="8" class="w-60 p-1">
      <div class="flex items-center gap-2 border-b border-border px-2 py-2">
        <span class="inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-sidebar-primary font-mono text-xs text-sidebar-primary-foreground">{{ user.initials }}</span>
        <div class="min-w-0">
          <div class="truncate text-sm font-medium">{{ user.name }}</div>
          <div class="truncate text-xs text-muted-foreground">{{ user.email }}</div>
        </div>
      </div>
      <div class="flex items-center gap-1.5 px-2 py-1.5 font-mono text-[11px] uppercase tracking-wide text-status-success">
        <span class="size-1.5 rounded-full bg-status-success" /> Conectada
      </div>
      <div class="my-1 h-px bg-border" />
      <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent"><UserRound class="size-4" /> Perfil</button>
      <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent"><Settings class="size-4" /> Preferencias</button>
      <button type="button" class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-destructive transition-colors hover:bg-accent"><LogOut class="size-4" /> Cerrar sesión</button>
    </PopoverContent>
  </Popover>
</template>
