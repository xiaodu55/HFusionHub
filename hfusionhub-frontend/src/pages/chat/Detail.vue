<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as conversationApi from '@/api/conversation'
import type { Conversation, Message } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { ArrowLeft, Send, User, Bot } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const conversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const loading = ref(false)
const sending = ref(false)
const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

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
    const res = await conversationApi.getConversationMessages(id, {
      pageNum: 1,
      pageSize: 100,
    })
    messages.value = res.data.records
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

  try {
    // 先添加用户消息到列表
    const userMessage: Message = {
      id: Date.now(),
      conversationId: Number(route.params.id),
      role: 'user',
      content,
      createTime: new Date().toISOString(),
    }
    messages.value.push(userMessage)
    await scrollToBottom()

    // 发送消息到后端
    const res = await conversationApi.sendMessage({
      conversationId: Number(route.params.id),
      content,
    })

    // 添加 AI 回复
    messages.value.push(res.data)
    await scrollToBottom()
  } catch (error) {
    console.error('发送消息失败:', error)
    // 移除用户消息如果发送失败
    messages.value.pop()
  } finally {
    sending.value = false
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const goBack = () => {
  router.push('/chat')
}

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
          {{ conversation ? new Date(conversation.createTime).toLocaleDateString() : '' }}
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
              <p class="whitespace-pre-wrap text-sm">{{ message.content }}</p>
              <p class="mt-1 text-xs opacity-70">
                {{ new Date(message.createTime).toLocaleTimeString() }}
              </p>
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
        <Button :disabled="!inputMessage.trim() || sending" @click="handleSend">
          <Send class="h-4 w-4" />
        </Button>
      </div>
    </div>
  </div>
</template>
