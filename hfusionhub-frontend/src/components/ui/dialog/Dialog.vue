<script setup lang="ts">
import { computed, provide } from 'vue'

interface Props {
  open?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const isOpen = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
})

provide('dialog-open', isOpen)
provide('dialog-close', () => {
  isOpen.value = false
})
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="fixed inset-0 z-50">
      <!-- 背景遮罩 -->
      <div
        class="fixed inset-0 bg-black/80"
        @click="isOpen = false"
      />
      <!-- 内容 -->
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <slot />
      </div>
    </div>
  </Teleport>
</template>
