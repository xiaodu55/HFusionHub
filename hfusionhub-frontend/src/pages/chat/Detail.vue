<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import * as conversationApi from '@/api/conversation'
import type { Conversation, Message } from '@/api/types'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { ArrowLeft, Send, User, Bot, Loader2, RotateCcw, Square, RefreshCw } from 'lucide-vue-next'
import { formatDateTime, formatTime } from '@/utils/date'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const conversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const loading = ref(false)
const sending = ref(false)
const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const streamingMessageId = ref<number | null>(null) // 正在流式输出的消息ID

// 用于取消流式请求的 AbortController
let abortController: AbortController | null = null

const loadConversation = async () => {
  const id = Number(route.params.id)
  try {
    const res = await conversationApi.getConversation(id)
    conversation.value = res.data
  } catch (error) {
    console.error('加载对话失败:', error)
  }
}

const loadMessages = async () => {
  loading.value = true
  const id = Number(route.params.id)
  try {
    const res = await conversationApi.getConversationMessages(id)
    messages.value = res.data
    await scrollToBottom()
  } catch (error) {
    console.error('加载消息失败:', error)
  } finally {
    loading.value = false
  }
}

const handleSend = async () => {
  if (!inputMessage.value.trim() || sending.value) return

  const content = inputMessage.value.trim()
  inputMessage.value = ''
  sending.value = true

  // 创建新的 AbortController
  abortController = new AbortController()

  try {
    // 1. 立即添加用户消息到列表
    const userMessage: Message = {
      id: Date.now(),
      conversationId: Number(route.params.id),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    }
    messages.value.push(userMessage)
    await scrollToBottom()

    // 2. 立即添加一个"思考中"的 assistant 消息占位符
    const pendingId = Date.now() + 1
    const pendingMessage: Message = {
      id: pendingId,
      conversationId: Number(route.params.id),
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
    }
    messages.value.push(pendingMessage)
    streamingMessageId.value = pendingId
    await scrollToBottom()

    // 3. 使用 fetch API 处理流式响应
    const response = await fetch('/api/conversation/message/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'satoken': userStore.token || '',
      },
      body: JSON.stringify({
        conversationId: Number(route.params.id),
        content,
      }),
      signal: abortController.signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No reader available')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let hasContent = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        // 支持 "data: " 和 "data:" 两种格式
        if (line.startsWith('data:')) {
          const data = line.slice(5).trim()
          if (data === '[DONE]') {
            // 流式响应完成，移除 streaming 状态
            streamingMessageId.value = null
          } else if (data) {
            try {
              const parsed = JSON.parse(data)
              const content = parsed.content || ''
              if (content) {
                hasContent = true
                // 更新已存在的消息内容
                const msg = messages.value.find(m => m.id === pendingId)
                if (msg) {
                  msg.content += content
                }
                await scrollToBottom()
              }
            } catch (e) {
              if (data) {
                hasContent = true
                const msg = messages.value.find(m => m.id === pendingId)
                if (msg) {
                  msg.content += data
                }
                await scrollToBottom()
              }
            }
          }
        }
      }
    }

    // 如果没有内容，移除占位消息
    if (!hasContent) {
      const index = messages.value.findIndex(m => m.id === pendingId)
      if (index !== -1) {
        messages.value.splice(index, 1)
      }
    }

    streamingMessageId.value = null

  } catch (error: any) {
    // 如果是用户取消，不显示错误
    if (error.name === 'AbortError') {
      console.log('Stream request cancelled')
      return
    }

    console.error('发送消息失败:', error)

    // 移除"思考中"的占位消息
    if (streamingMessageId.value) {
      const index = messages.value.findIndex(m => m.id === streamingMessageId.value)
      if (index !== -1) {
        messages.value.splice(index, 1)
      }
      streamingMessageId.value = null
    }

    // 回退到普通请求
    try {
      const res = await conversationApi.sendMessage({
        conversationId: Number(route.params.id),
        content,
      })
      messages.value.push(res.data)
      await scrollToBottom()
    } catch (fallbackError) {
      console.error('Fallback request failed:', fallbackError)
      // 移除用户消息如果发送失败
      messages.value.pop()
    }
  } finally {
    sending.value = false
    streamingMessageId.value = null
    abortController = null
  }
}

const scrollToBottom = async () => {
  await nextTick()
  await nextTick()
  await new Promise(resolve => setTimeout(resolve, 100))
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const goBack = () => {
  router.push('/chat')
}

// 停止生成
const handleStopGeneration = () => {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  // 保留已生成的内容，只停止流式输出
  streamingMessageId.value = null
  sending.value = false
}

// 重试消息
const handleRetryMessage = async (message: Message) => {
  if (sending.value) return

  // 找到这条消息的前一条用户消息
  const messageIndex = messages.value.findIndex(m => m.id === message.id)
  if (messageIndex <= 0) return

  const userMessage = messages.value[messageIndex - 1]
  if (!userMessage || userMessage.role !== 'user') return

  // 移除这条失败的消息
  messages.value.splice(messageIndex, 1)

  // 重新发送用户消息
  inputMessage.value = userMessage.content
  // 移除用户消息（因为 handleSend 会重新添加）
  messages.value.splice(messageIndex - 1, 1)
  await handleSend()
}

// 判断消息是否为错误消息
const isErrorMessage = (message: Message) => {
  return message.role === 'assistant' &&
    (message.model === 'error' || message.content?.includes('抱歉，AI服务暂时不可用'))
}

// 监听消息变化，自动滚动到底部
watch(
  () => messages.value.length,
  async () => {
    await scrollToBottom()
  }
)

// 取消正在进行的流式请求
const cancelOngoingRequests = () => {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  streamingMessageId.value = null
  sending.value = false
}

// 组件卸载时取消请求
onUnmounted(() => {
  cancelOngoingRequests()
})

// 路由离开时取消请求
onBeforeRouteLeave(() => {
  cancelOngoingRequests()
})

onMounted(() => {
  loadConversation()
  loadMessages()
})
</script>

<template>
  <div class="flex h-[calc(100vh-8rem)] flex-col">
    <!-- 头部 -->
    <div class="flex items-center gap-4 border-b pb-4">
      <Button variant="ghost" size="icon" @click="goBack">
        <ArrowLeft class="h-5 w-5" />
      </Button>
      <div>
        <h2 class="text-lg font-semibold">{{ conversation?.title || '对话' }}</h2>
        <p class="text-sm text-muted-foreground">
          {{ conversation ? formatDateTime(conversation.createdAt) : '' }}
        </p>
      </div>
    </div>

    <!-- 消息区域 -->
    <div
      ref="messagesContainer"
      class="flex-1 overflow-auto p-4 space-y-4"
    >
      <div v-if="loading" class="text-center text-muted-foreground py-8">
        加载中...
      </div>
      <div v-else-if="messages.length === 0" class="text-center py-8">
        <Bot class="mx-auto h-12 w-12 text-muted-foreground" />
        <p class="mt-4 text-muted-foreground">开始与 AI 对话吧</p>
      </div>
      <template v-else>
        <div
          v-for="message in messages"
          :key="message.id"
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
              <template v-if="streamingMessageId === message.id">
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
                  <p class="whitespace-pre-wrap text-sm">{{ message.content }}</p>
                </template>
                <div class="flex items-center justify-between mt-1">
                  <p class="text-xs opacity-70">
                    {{ formatTime(message.createdAt) }}
                  </p>
                  <!-- 重试按钮（仅在错误消息和助手消息上显示） -->
                  <Button
                    v-if="message.role === 'assistant' && !streamingMessageId"
                    variant="ghost"
                    size="sm"
                    class="h-6 px-2 text-xs"
                    @click="handleRetryMessage(message)"
                  >
                    <RefreshCw class="h-3 w-3 mr-1" />
                    重试
                  </Button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 输入区域 -->
    <div class="border-t pt-4">
      <div class="flex gap-2">
        <Input
          v-model="inputMessage"
          placeholder="输入消息..."
          :disabled="sending"
          @keyup.enter="handleSend"
        />
        <!-- 停止生成按钮 -->
        <Button
          v-if="sending"
          variant="destructive"
          @click="handleStopGeneration"
        >
          <Square class="h-4 w-4 mr-2" />
          停止生成
        </Button>
        <!-- 发送按钮 -->
        <Button v-else :disabled="!inputMessage.trim()" @click="handleSend">
          <Send class="h-4 w-4" />
        </Button>
      </div>
    </div>
  </div>
</template>
