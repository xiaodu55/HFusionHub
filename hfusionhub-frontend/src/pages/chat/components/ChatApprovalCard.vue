<script setup lang="ts">
import { computed } from 'vue'
import { Check, Loader2, Pencil, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

export interface ChatApprovalPrompt {
  toolName?: string
  argumentsSummary?: string
}

const props = defineProps<{
  prompt: ChatApprovalPrompt
  busy: boolean
}>()

const emit = defineEmits<{
  decide: [action: 'approved' | 'denied']
}>()

const summaryText = computed(() =>
  props.prompt.toolName === 'write_note'
    ? '把内容整理成笔记保存到知识库'
    : `调用工具 ${props.prompt.toolName ?? '未知工具'}`
)
</script>

<template>
  <div class="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
    <div class="flex items-start gap-3">
      <Pencil class="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-medium text-amber-600">需要你的确认</p>
        <p class="mt-1 text-sm text-foreground">
          Agent 请求{{ summaryText }}，是否允许执行？
        </p>
        <p v-if="prompt.argumentsSummary" class="mt-1 line-clamp-3 text-xs text-muted-foreground">
          {{ prompt.argumentsSummary }}
        </p>
        <div class="mt-3 flex items-center gap-2">
          <Button size="sm" variant="default" :disabled="busy" @click="emit('decide', 'approved')">
            <Check class="mr-1 h-4 w-4" /> 同意执行
          </Button>
          <Button size="sm" variant="outline" :disabled="busy" @click="emit('decide', 'denied')">
            <X class="mr-1 h-4 w-4" /> 拒绝
          </Button>
          <Loader2 v-if="busy" class="ml-1 h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      </div>
    </div>
  </div>
</template>
