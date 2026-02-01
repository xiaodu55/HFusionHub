<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'
import { badgeVariants, type BadgeVariants } from './index'

interface Props {
  variant?: BadgeVariants['variant']
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <div :class="cn(badgeVariants(props), props.class)" v-bind="delegatedProps">
    <slot />
  </div>
</template>
