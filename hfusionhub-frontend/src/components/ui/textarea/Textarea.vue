<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

interface Props {
  class?: string
  modelValue?: string
  placeholder?: string
  rows?: number
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  rows: 4,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const delegatedProps = computed(() => {
  const { class: _, modelValue, ...delegated } = props
  return delegated
})

const onInput = (event: Event) => {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <textarea
    :class="cn(
      'flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
      props.class
    )"
    :value="modelValue"
    v-bind="delegatedProps"
    @input="onInput"
  />
</template>
