<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'
import { buttonVariants, type ButtonVariants } from './index'

interface Props {
  variant?: ButtonVariants['variant']
  size?: ButtonVariants['size']
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'default',
})

const delegatedProps = computed(() => {
  const { class: _, ...delegated } = props
  return delegated
})
</script>

<template>
  <button :class="cn(buttonVariants(props), props.class)" v-bind="delegatedProps">
    <slot />
  </button>
</template>
