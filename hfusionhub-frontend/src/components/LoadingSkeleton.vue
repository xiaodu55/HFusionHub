<script setup lang="ts">
interface Props {
  /** Type of skeleton to show */
  type?: 'card' | 'list' | 'table' | 'chat'
  /** Number of skeleton items to render */
  count?: number
}

withDefaults(defineProps<Props>(), {
  type: 'card',
  count: 3,
})
</script>

<template>
  <!-- Card grid skeleton -->
  <div v-if="type === 'card'" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
    <div
      v-for="i in count"
      :key="i"
      class="rounded-lg border bg-card p-5 animate-pulse"
    >
      <div class="h-4 w-3/4 rounded bg-muted" />
      <div class="mt-3 h-3 w-1/2 rounded bg-muted" />
      <div class="mt-4 space-y-2">
        <div class="h-3 rounded bg-muted" />
        <div class="h-3 w-5/6 rounded bg-muted" />
      </div>
    </div>
  </div>

  <!-- List skeleton -->
  <div v-else-if="type === 'list'" class="space-y-3">
    <div
      v-for="i in count"
      :key="i"
      class="flex items-center gap-4 rounded-lg border bg-card p-4 animate-pulse"
    >
      <div class="h-10 w-10 shrink-0 rounded-full bg-muted" />
      <div class="flex-1 space-y-2">
        <div class="h-4 w-1/3 rounded bg-muted" />
        <div class="h-3 w-2/3 rounded bg-muted" />
      </div>
      <div class="h-4 w-16 rounded bg-muted" />
    </div>
  </div>

  <!-- Table skeleton -->
  <div v-else-if="type === 'table'" class="space-y-3">
    <!-- Header -->
    <div class="flex gap-4 rounded-lg border bg-muted/30 p-4 animate-pulse">
      <div v-for="j in 4" :key="'h'+j" class="h-4 rounded bg-muted" :style="{ width: `${100 / (j + 1)}%` }" />
    </div>
    <!-- Rows -->
    <div
      v-for="i in count"
      :key="i"
      class="flex gap-4 rounded-lg border bg-card p-4 animate-pulse"
    >
      <div v-for="j in 4" :key="'r'+i+'-'+j" class="h-3 rounded bg-muted" :style="{ width: `${80 / (j + 1)}%` }" />
    </div>
  </div>

  <!-- Chat message skeleton -->
  <div v-else-if="type === 'chat'" class="space-y-6 px-4">
    <div v-for="i in count" :key="i" class="flex gap-3" :class="i % 2 === 0 ? 'justify-end' : ''">
      <div v-if="i % 2 !== 0" class="h-8 w-8 shrink-0 rounded-full bg-muted animate-pulse" />
      <div class="max-w-[70%] space-y-2 rounded-lg px-4 py-3" :class="i % 2 === 0 ? 'bg-primary/10' : 'bg-muted/50'">
        <div class="h-3 rounded bg-muted-foreground/20 animate-pulse" :style="{ width: `${60 + Math.random() * 30}%` }" />
        <div class="h-3 rounded bg-muted-foreground/20 animate-pulse" :style="{ width: `${40 + Math.random() * 40}%` }" />
        <div v-if="i % 2 !== 0" class="h-3 w-1/2 rounded bg-muted-foreground/20 animate-pulse" />
      </div>
      <div v-if="i % 2 === 0" class="h-8 w-8 shrink-0 rounded-full bg-muted animate-pulse" />
    </div>
  </div>
</template>
