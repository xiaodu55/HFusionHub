<script setup lang="ts">
/**
 * EmbedChat — 可嵌入聊天挂件（Batch 6 发布渠道）。
 *
 * 用法：`<iframe src="https://<host>/embed/chat?key=<开放API Key>">`
 * 无需登录态；鉴权完全走开放 API Key（Authorization: Bearer <key>），
 * 服务端复用 app_api_key → 已发布应用 → 绑定知识库的完整链路。
 */
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const route = useRoute()
const apiKey = String(route.query.key ?? '')

const messages = ref<ChatMessage[]>([])
const draft = ref('')
const streaming = ref(false)
const listEl = ref<HTMLElement | null>(null)
let abortController: AbortController | null = null

function renderMarkdown(content: string): string {
  return DOMPurify.sanitize(marked.parse(content) as string)
}

async function scrollToBottom() {
  await nextTick()
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight })
}

function appendUser(text: string) {
  messages.value.push({ role: 'user', content: text })
}

function appendAssistantDelta(delta: string) {
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    last.content += delta
  } else {
    messages.value.push({ role: 'assistant', content: delta })
  }
}

/** 解析 openapi SSE：data 行为 JSON 事件或 [DONE]（与 /openapi/chat/stream 契约一致） */
async function streamAnswer(text: string) {
  streaming.value = true
  appendAssistantDelta('')
  try {
    abortController = new AbortController()
    const response = await fetch('/api/openapi/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        query: text,
        history: messages.value
          .slice(0, -1)
          .filter((m) => m.content)
          .slice(-10)
          .map((m) => ({ role: m.role, content: m.content })),
      }),
      signal: abortController.signal,
    })
    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const raw of lines) {
        const line = raw.trim()
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (!payload) continue
        if (payload === '[DONE]') continue
        try {
          const event = JSON.parse(payload)
          const delta = String(event.content ?? '')
          if (delta && !event.error) appendAssistantDelta(delta)
          if (event.cancelled) appendAssistantDelta('\n（已取消）')
        } catch {
          /* 忽略无法解析的行 */
        }
      }
      scrollToBottom()
    }
  } catch (error) {
    if ((error as Error).name !== 'AbortError') {
      appendAssistantDelta('服务暂时不可用，请稍后重试。')
    }
  } finally {
    streaming.value = false
    abortController = null
    scrollToBottom()
  }
}

async function send() {
  const text = draft.value.trim()
  if (!text || streaming.value) return
  if (!apiKey) {
    appendUser(text)
    appendAssistantDelta('缺少 API Key：请在挂件地址中携带 ?key=<开放API Key>。')
    return
  }
  draft.value = ''
  appendUser(text)
  scrollToBottom()
  await streamAnswer(text)
}

function stop() {
  abortController?.abort()
}

onBeforeUnmount(() => abortController?.abort())
</script>

<template>
  <div class="flex h-screen w-full flex-col bg-white text-sm">
    <header class="flex items-center gap-2 border-b px-4 py-3 text-base font-medium">
      <span>AI 助手</span>
      <span class="text-xs text-muted-foreground">由 HFusionHub 驱动</span>
    </header>

    <div ref="listEl" class="flex-1 space-y-4 overflow-y-auto px-4 py-4">
      <div v-if="messages.length === 0" class="mt-10 text-center text-muted-foreground">
        你好，请输入你的问题。
      </div>
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="flex"
        :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div
          class="max-w-[85%] rounded-2xl px-4 py-2 leading-relaxed"
          :class="
            message.role === 'user'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted'
          "
        >
          <template v-if="message.role === 'assistant'">
            <div class="prose prose-sm max-w-none" v-html="renderMarkdown(message.content)" />
          </template>
          <template v-else>{{ message.content }}</template>
        </div>
      </div>
    </div>

    <div class="border-t p-3">
      <div class="flex items-end gap-2">
        <textarea
          v-model="draft"
          rows="1"
          placeholder="输入消息…"
          class="max-h-32 flex-1 resize-none rounded-lg border px-3 py-2 outline-none focus:ring-1"
          :disabled="streaming"
          @keydown.enter.exact.prevent="send"
        />
        <button
          v-if="!streaming"
          class="rounded-lg bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
          :disabled="!draft.trim()"
          @click="send"
        >
          发送
        </button>
        <button
          v-else
          class="rounded-lg border px-4 py-2"
          @click="stop"
        >
          停止
        </button>
      </div>
    </div>
  </div>
</template>
