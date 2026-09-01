<script setup lang="ts">
import { Copy, Loader2, RefreshCw, Square, ThumbsDown, ThumbsUp, User, Bot, Volume2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import KnowledgeSources from './KnowledgeSources.vue'
import { formatTime } from '@/utils/date'
import type { Message } from '@/api/types'

const props = defineProps<{
  message: Message
  /** 该消息正在流式生成中 */
  streaming: boolean
  /** 会话是否处于任一流式生成中（隐藏重新生成/重试按钮） */
  sessionStreaming: boolean
  feedback?: 'UP' | 'DOWN'
  ttsEnabled: boolean
  speaking: boolean
  knowledgeBaseId?: number | null
}>()

const emit = defineEmits<{
  copy: [message: Message]
  speak: [messageId: string, content: string]
  regenerate: [message: Message]
  retry: [message: Message]
  'feedback-up': [message: Message]
  'feedback-down-open': [message: Message]
  'image-load': []
}>()

// 判断消息是否为错误消息
const isErrorMessage = (m: Message) => {
  return m.role === 'assistant' &&
    (m.model === 'error' || m.content?.includes('抱歉，AI服务暂时不可用'))
}

const speakingId = () => String(props.message.id)
</script>

<template>
  <div
    :class="[
      'flex gap-3',
      message.role === 'user' ? 'justify-end' : 'justify-start'
    ]"
  >
    <div
      :class="[
        'flex items-start gap-2 max-w-[80%]',
        message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
      ]"
    >
      <div
        :class="[
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          message.role === 'user'
            ? 'bg-primary text-primary-foreground'
            : 'bg-secondary text-secondary-foreground'
        ]"
      >
        <User v-if="message.role === 'user'" class="h-4 w-4" />
        <Bot v-else class="h-4 w-4" />
      </div>
      <div
        :class="[
          'rounded-lg px-4 py-2',
          message.role === 'user'
            ? 'bg-primary text-primary-foreground'
            : 'bg-secondary text-secondary-foreground'
        ]"
      >
        <!-- 流式输出中的消息 -->
        <template v-if="streaming">
          <template v-if="message.content">
            <MarkdownRenderer :content="message.content" class="text-sm" />
            <div class="flex items-center gap-2 mt-2">
              <Loader2 class="h-3 w-3 animate-spin" />
              <span class="text-xs text-muted-foreground">生成中...</span>
            </div>
          </template>
          <template v-else>
            <div class="flex items-center gap-2">
              <Loader2 class="h-4 w-4 animate-spin" />
              <span class="text-sm">思考中...</span>
            </div>
          </template>
        </template>
        <!-- 普通消息 -->
        <template v-else>
          <template v-if="message.role === 'assistant'">
            <MarkdownRenderer :content="message.content" class="text-sm" />
          </template>
          <template v-else>
            <div v-if="message.images?.length" class="mb-1 flex flex-wrap gap-1.5">
              <img
                v-for="(src, i) in message.images"
                :key="i"
                :src="src"
                class="max-h-36 rounded border border-background/20"
                alt="用户上传的图片"
                @load="emit('image-load')"
              />
            </div>
            <p v-if="message.content" class="whitespace-pre-wrap text-sm">{{ message.content }}</p>
          </template>
          <div class="flex items-center justify-between gap-2 mt-1">
            <p class="text-xs opacity-70">
              {{ formatTime(message.createdAt) }}
              <span
                v-if="message.role === 'assistant' && message.model && message.model !== 'error' && message.model !== 'streaming'"
                class="ml-1.5 inline-block rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary"
              >
                {{ message.model }}
              </span>
            </p>
            <div class="flex items-center gap-0.5">
              <Button
                variant="ghost"
                size="icon"
                class="h-7 w-7 text-muted-foreground hover:text-foreground"
                title="复制内容"
                @click="emit('copy', message)"
              >
                <Copy class="h-3.5 w-3.5" />
              </Button>
              <Button
                v-if="ttsEnabled && message.id > 0 && message.content && !isErrorMessage(message)"
                variant="ghost"
                size="icon"
                class="h-7 w-7 text-muted-foreground hover:text-primary"
                :title="speaking ? '停止播报' : '语音播报'"
                @click="emit('speak', speakingId(), message.content)"
              >
                <Volume2 v-if="!speaking" class="h-3.5 w-3.5" />
                <Square v-else class="h-3.5 w-3.5" />
              </Button>
              <template v-if="message.role === 'assistant' && message.id > 0 && !isErrorMessage(message) && !sessionStreaming">
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-7 w-7 text-muted-foreground hover:text-primary"
                  title="重新生成回答"
                  @click="emit('regenerate', message)"
                >
                  <RefreshCw class="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-7 w-7"
                  :class="feedback === 'UP' ? 'text-emerald-400' : 'text-muted-foreground'"
                  title="回答有帮助"
                  @click="emit('feedback-up', message)"
                >
                  <ThumbsUp class="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-7 w-7"
                  :class="feedback === 'DOWN' ? 'text-rose-400' : 'text-muted-foreground'"
                  title="回答需要改进"
                  @click="emit('feedback-down-open', message)"
                >
                  <ThumbsDown class="h-3.5 w-3.5" />
                </Button>
              </template>
              <!-- 重试按钮（仅在错误消息上显示） -->
              <Button
                v-if="isErrorMessage(message) && !sessionStreaming"
                variant="ghost"
                size="sm"
                class="h-6 px-2 text-xs"
                @click="emit('retry', message)"
              >
                <RefreshCw class="h-3 w-3 mr-1" />
                重试
              </Button>
            </div>
          </div>
        </template>

        <!-- 知识来源（流式输出期间与完成后都会显示） -->
        <KnowledgeSources
          v-if="message.role === 'assistant' && message.sources && message.sources.length > 0"
          :sources="message.sources"
          :knowledge-base-id="knowledgeBaseId"
        />
      </div>
    </div>
  </div>
</template>
