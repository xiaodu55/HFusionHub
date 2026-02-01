<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  class?: string
}

const props = defineProps<Props>()

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <h3
    :class="cn(
      'text-2xl font-semibold leading-none tracking-tight',
      props.class
    )"
    v-bind="delegatedProps"
  >
    <slot />
  </h3>
</template>
