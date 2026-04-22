<script setup lang="ts">
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

withDefaults(defineProps<{
  open: boolean
  title?: string
  description?: string
  confirmText?: string
  destructive?: boolean
  loading?: boolean
}>(), {
  title: '确认操作',
  confirmText: '确认',
  destructive: false,
  loading: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: []
}>()
</script>

<template>
  <Dialog :open="open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription v-if="description">{{ description }}</DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" :disabled="loading" @click="emit('update:open', false)">取消</Button>
        <Button :variant="destructive ? 'destructive' : 'default'" :disabled="loading" @click="emit('confirm')">
          {{ loading ? '处理中...' : confirmText }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
