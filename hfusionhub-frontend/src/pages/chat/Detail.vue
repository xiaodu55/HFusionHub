<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import * as conversationApi from '@/api/conversation'
import { getAnswerFeedback, saveAnswerFeedback } from '@/api/rag'
import { listPendingApprovals, decideApproval, type AgentApproval } from '@/api/approval'
import type { Conversation, Message } from '@/api/types'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ArrowLeft, BookOpen, Check, Copy, Download, Eraser, Pencil, Send, User, Bot, Loader2, Square, RefreshCw, ThumbsUp, ThumbsDown, X } from 'lucide-vue-next'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useToast } from '@/composables/useToast'
import { formatDateTime, formatTime } from '@/utils/date'
import { friendlyErrorMessage } from '@/utils/errorMessage'
import { SseDataParser, type SseDataEvent } from '@/utils/sse'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const toast = useToast()

const conversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const feedbackByMessage = ref<Record<number, 'UP' | 'DOWN'>>({})
const feedbackDialogOpen = ref(false)
const feedbackMessage = ref<Message | null>(null)
const feedbackReason = ref('')
const expectedAnswer = ref('')
const feedbackSaving = ref(false)
const loading = ref(false)
const sending = ref(false)
const inputMessage = ref('')
const isComposing = ref(false) // 中文输入法组合态：组合期间按 Enter 不发送
const messagesContainer = ref<HTMLElement | null>(null)
const streamingMessageId = ref<number | null>(null) // 正在流式输出的消息ID

// ── 工具调用审批确认（write_note 等写工具）──────────────────────────
const approvalPrompt = ref<AgentApproval | null>(null) // 待确认的审批
const approvalBusy = ref(false) // 确认按钮处理中
let lastApprovalCheck = 0 // 防抖：同一时间窗只检查一次

/** 检查是否有刚产生的待审批（最近 3 分钟内），有则弹出确认卡片。 */
const maybeCheckApproval = async () => {
  try {
    const now = Date.now()
    if (now - lastApprovalCheck < 2000) return // 2s 防抖
    lastApprovalCheck = now
    const res = await listPendingApprovals()
    const pending = (res.data || []).filter(a => {
      if (a.status !== 'pending') return false
      const created = new Date(a.createdAt).getTime()
      return now - created < 3 * 60 * 1000 // 最近 3 分钟
    })
    // 优先展示 write_note 相关的审批
    const target = pending.find(a => a.toolName === 'write_note') || pending[0]
    if (target) approvalPrompt.value = target
  } catch {
    // 静默失败：不打断聊天
  }
}

/** 用户点击同意/拒绝 → 调用审批决定接口，Agent 将继续/终止执行。 */
const handleApprovalDecision = async (decision: 'approved' | 'denied') => {
  const approval = approvalPrompt.value
  if (!approval || !approval.taskId) return
  approvalBusy.value = true
  try {
    await decideApproval(approval.taskId, {
      approvalId: approval.approvalId,
      decision,
      reason: decision === 'approved' ? '用户在聊天中确认' : '用户在聊天中拒绝',
    })
    toast.success(decision === 'approved' ? '已批准，Agent 将继续执行' : '已拒绝')
    approvalPrompt.value = null
    // 批准后 Agent 恢复执行，稍后刷新消息
    if (decision === 'approved') {
      setTimeout(() => loadMessages(true), 2500)
    }
  } catch (e) {
    toast.error(friendlyErrorMessage(e, '审批操作失败，请稍后重试'))
  } finally {
    approvalBusy.value = false
  }
}

// 用于取消流式请求的 AbortController
let abortController: AbortController | null = null
let activeRequestId: string | null = null

const loadConversation = async () => {
  const id = Number(route.params.id)
  try {
    const res = await conversationApi.getConversation(id)
    conversation.value = res.data
  } catch (error) {
    console.error('加载对话失败:', error)
  }
}

const loadMessages = async (silent = false) => {
  // silent：流式结束后的增量刷新——不显示骨架屏、保持滚动位置，避免整表闪烁
  if (!silent) loading.value = true
  const id = Number(route.params.id)
  try {
    const res = await conversationApi.getConversationMessages(id)
    messages.value = res.data
    try {
      const feedback = await getAnswerFeedback(id)
      feedbackByMessage.value = Object.fromEntries(
        feedback.data.map(item => [item.messageId, item.rating]),
      )
    } catch {
      feedbackByMessage.value = {}
    }
    if (silent) {
      await nextTick()
      await nextTick()
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    } else {
      await scrollToBottom()
    }
  } catch (error) {
    console.error('加载消息失败:', error)
  } finally {
    if (!silent) loading.value = false
  }
}

const handleSend = async () => {
  if (isComposing.value) return
  if (!inputMessage.value.trim() || sending.value) return

  const content = inputMessage.value.trim()
  inputMessage.value = ''
  sending.value = true

  // 创建新的 AbortController
  abortController = new AbortController()
  const requestId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
  let pendingId: number | null = null

  // 北京时间字符串 — 定义在 try 外以便 catch 块中错误消息使用
  const now = new Date()
  const beijingTime = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000)
  const timeStr = `${beijingTime.getFullYear()}-${String(beijingTime.getMonth() + 1).padStart(2, '0')}-${String(beijingTime.getDate()).padStart(2, '0')} ${String(beijingTime.getHours()).padStart(2, '0')}:${String(beijingTime.getMinutes()).padStart(2, '0')}:${String(beijingTime.getSeconds()).padStart(2, '0')}`

  try {
    // 1. 立即添加用户消息到列表
    const userMessage: Message = {
      id: Date.now(),
      conversationId: Number(route.params.id),
      role: 'user',
      content,
      createdAt: timeStr,
    }
    messages.value.push(userMessage)
    await scrollToBottom()

    // 2. 立即添加一个"思考中"的 assistant 消息占位符（使用北京时间）
    pendingId = Date.now() + 1
    const pendingMessage: Message = {
      id: pendingId,
      conversationId: Number(route.params.id),
      role: 'assistant',
      content: '',
      createdAt: timeStr,
    }
    messages.value.push(pendingMessage)
    streamingMessageId.value = pendingId
    activeRequestId = requestId
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
        requestId,
        // KB 会话启用写能力：模型可见 write_note（写工具），调用前会请求人工审批
        capabilityProfile: conversation.value?.knowledgeBaseId ? 'approval_write' : undefined,
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
    const parser = new SseDataParser()
    let hasContent = false

    const applyStreamEvents = async (events: SseDataEvent[]) => {
      for (const event of events) {
        if (event.type === 'done') {
          streamingMessageId.value = null
          continue
        }

        try {
          const parsed = JSON.parse(event.data)
          const contentDelta = parsed.content || ''
          const sources = parsed.sources || []

          if (contentDelta) {
            hasContent = true
            const msg = messages.value.find(m => m.id === pendingId)
            if (msg) {
              // 内容安全守卫矫正事件：整段替换已累计内容，而非追加
              // （Java 桥接转发 replace:"true"；直连 Python 时为 content_replace:true）
              const isReplace =
                parsed.content_replace === true ||
                parsed.replace === true ||
                parsed.replace === 'true'
              if (isReplace) {
                msg.content = contentDelta
              } else {
                msg.content += contentDelta
              }
            }
            await scrollToBottom()
          }

          if (sources.length > 0) {
            const msg = messages.value.find(m => m.id === pendingId)
            if (msg) {
              msg.sources = sources
            }
          }
        } catch {
          hasContent = true
          const msg = messages.value.find(m => m.id === pendingId)
          if (msg) {
            msg.content += event.data
          }
          await scrollToBottom()
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      await applyStreamEvents(parser.push(decoder.decode(value, { stream: true })))
    }
    await applyStreamEvents(parser.push(decoder.decode()))
    await applyStreamEvents(parser.flush())

    // 如果没有内容，移除占位消息
    if (!hasContent) {
      const index = messages.value.findIndex(m => m.id === pendingId)
      if (index !== -1) {
        messages.value.splice(index, 1)
      }
    }

    streamingMessageId.value = null
    // SSE uses a temporary client ID; reload once so feedback targets the persisted assistant message.
    await loadMessages(true)

  } catch (error: any) {
    // 如果是用户取消，不显示错误
    if (error.name === 'AbortError') {
      const index = pendingId === null ? -1 : messages.value.findIndex(m => m.id === pendingId)
      if (index !== -1 && !messages.value[index].content) {
        messages.value.splice(index, 1)
      }
      console.log('Stream request cancelled')
      return
    }

    console.error('发送消息失败:', error)

    // 保留已流式接收的部分内容；仅移除完全为空的占位消息
    if (pendingId !== null) {
      const index = messages.value.findIndex(m => m.id === pendingId)
      if (index !== -1) {
        if (messages.value[index].content) {
          // 有部分内容——保留并在尾部追加"回复中断"标记
          messages.value[index].content += '\n\n⚠️ 回复中断，请重试。'
        } else {
          // 完全为空——移除占位
          messages.value.splice(index, 1)
        }
      }
      streamingMessageId.value = null
    }

    // 回退到普通请求
    try {
      const res = await conversationApi.sendMessage({
        conversationId: Number(route.params.id),
        content,
        requestId,
        capabilityProfile: conversation.value?.knowledgeBaseId ? 'approval_write' : undefined,
      })
      // 如果占位消息还在（有部分内容），替换为新完整回复
      if (pendingId !== null) {
        const idx = messages.value.findIndex(m => m.id === pendingId)
        if (idx !== -1) {
          messages.value[idx] = res.data
        } else {
          messages.value.push(res.data)
        }
      } else {
        messages.value.push(res.data)
      }
      await scrollToBottom()
    } catch (fallbackError) {
      console.error('Fallback request failed:', fallbackError)
      // 确保至少有一个错误提示在对话中
      const errIdx = pendingId !== null ? messages.value.findIndex(m => m.id === pendingId) : -1
      if (errIdx === -1) {
        const reason = friendlyErrorMessage(fallbackError, '消息发送失败，请稍后重试')
        messages.value.push({
          id: Date.now() + 1,
          conversationId: Number(route.params.id),
          role: 'assistant' as const,
          content: `⚠️ ${reason}${reason.includes('AI 服务') ? '' : '\n\n若 AI 服务未就绪，可在「设置」中查看服务状态，或在「模型中心」确认模型配置。'}`,
          model: 'error',
          createdAt: timeStr,
        })
      }
    }
  } finally {
    sending.value = false
    streamingMessageId.value = null
    abortController = null
    if (activeRequestId === requestId) {
      activeRequestId = null
    }
    // 工具调用可能已产生待审批（如 write_note），延迟检查并弹出确认卡片
    setTimeout(maybeCheckApproval, 1500)
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
const cancelRemoteStream = async () => {
  const requestId = activeRequestId
  if (!requestId) return

  try {
    await conversationApi.cancelStream(requestId)
  } catch (error) {
    // 浏览器断开时后端也会收到 SSE completion，远程取消失败不应阻塞本地停止。
    console.warn('远程取消流式请求失败:', error)
  }
}

const handleStopGeneration = async () => {
  const controller = abortController
  await cancelRemoteStream()
  controller?.abort()
  abortController = null
  // 保留已生成的内容，只停止流式输出
  streamingMessageId.value = null
  sending.value = false
}

// 重试消息（先在服务端删除失败轮次，避免重复）
const handleRetryMessage = async (message: Message) => {
  if (sending.value) return

  // 找到这条消息的前一条用户消息
  const messageIndex = messages.value.findIndex(m => m.id === message.id)
  if (messageIndex <= 0) return

  const userMessage = messages.value[messageIndex - 1]
  if (!userMessage || userMessage.role !== 'user') return

  // 服务端删除旧轮次（失败回答 + 对应提问），防止重试后重复
  const conversationId = Number(route.params.id)
  if (message.id > 0) {
    try { await conversationApi.deleteConversationMessage(conversationId, message.id) } catch { /* 忽略删除失败 */ }
  }
  if (userMessage.id > 0) {
    try { await conversationApi.deleteConversationMessage(conversationId, userMessage.id) } catch { /* 忽略删除失败 */ }
  }

  // 移除这条失败的消息
  messages.value.splice(messageIndex, 1)

  // 重新发送用户消息
  inputMessage.value = userMessage.content
  // 移除用户消息（因为 handleSend 会重新添加）
  messages.value.splice(messageIndex - 1, 1)
  await handleSend()
}

// 重新生成：服务端删除旧问答对后重新发送提问（不产生重复轮次）
const regenerateMessage = async (message: Message) => {
  if (sending.value) return

  const messageIndex = messages.value.findIndex(m => m.id === message.id)
  if (messageIndex <= 0) return

  const userMessage = messages.value[messageIndex - 1]
  if (!userMessage || userMessage.role !== 'user') return

  const conversationId = Number(route.params.id)
  if (message.id > 0) {
    try { await conversationApi.deleteConversationMessage(conversationId, message.id) } catch { /* 忽略删除失败 */ }
  }
  if (userMessage.id > 0) {
    try { await conversationApi.deleteConversationMessage(conversationId, userMessage.id) } catch { /* 忽略删除失败 */ }
  }

  messages.value.splice(messageIndex, 1)
  messages.value.splice(messageIndex - 1, 1)
  inputMessage.value = userMessage.content
  await handleSend()
}

// 复制消息内容（优先 Clipboard API，失败时降级到 execCommand）
const copyMessage = async (message: Message) => {
  const text = message.content || ''
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      toast.success('已复制到剪贴板')
      return
    }
    throw new Error('clipboard unavailable')
  } catch {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败，请手动选择文本复制')
    }
  }
}

// 空会话时的示例问题（点击后填入输入框；区分关联知识库与通用对话）
const examplePrompts = computed(() =>
  conversation.value?.knowledgeBaseId
    ? [
        '总结一下这个知识库的核心内容',
        '我的产品有哪些主要特点？',
        '帮我起草一份问题处理流程说明',
        '知识库中提到了哪些注意事项？',
      ]
    : [
        '你好，介绍一下你自己',
        '你能帮我做什么？',
        '如何创建知识库并上传文档？',
        '什么是 RAG？请举例说明',
      ],
)
const fillExamplePrompt = (prompt: string) => {
  inputMessage.value = prompt
  document.querySelector<HTMLInputElement>('#chat-input')?.focus()
}

// ── 会话重命名 / 清空 ──
const renameDialogOpen = ref(false)
const renameTitle = ref('')
const clearDialogOpen = ref(false)

const openRenameDialog = () => {
  renameTitle.value = conversation.value?.title || ''
  renameDialogOpen.value = true
}

const submitRename = async () => {
  const title = renameTitle.value.trim()
  if (!title || !conversation.value) {
    toast.error('对话名称不能为空')
    return
  }
  try {
    await conversationApi.renameConversation(conversation.value.id, title)
    conversation.value.title = title
    renameDialogOpen.value = false
    toast.success('对话已重命名')
  } catch (error) {
    toast.error(friendlyErrorMessage(error, '重命名失败'))
  }
}

const submitClear = async () => {
  if (!conversation.value) return
  try {
    await conversationApi.clearConversationMessages(conversation.value.id)
    messages.value = []
    feedbackByMessage.value = {}
    clearDialogOpen.value = false
    toast.success('对话已清空')
  } catch (error) {
    toast.error(friendlyErrorMessage(error, '清空失败'))
  }
}

// 导出对话为 Markdown（纯前端）
const exportConversation = () => {
  if (!conversation.value || messages.value.length === 0) return
  const lines: string[] = []
  lines.push(`# ${conversation.value.title || '对话导出'}`)
  lines.push(`- 创建时间：${formatDateTime(conversation.value.createdAt)}`)
  lines.push(`- 知识库：${conversation.value.knowledgeBaseName || '通用对话'}`)
  if (conversation.value.promptTemplateName) lines.push(`- 回答方案：${conversation.value.promptTemplateName}`)
  lines.push('')
  for (const message of messages.value) {
    const role = message.role === 'user' ? '👤 用户' : '🤖 AI'
    lines.push(`## ${role} · ${formatTime(message.createdAt)}`)
    lines.push('')
    lines.push(message.content || '')
    if (message.sources?.length) {
      const names = message.sources.map(s => s.document_name || s.title).filter(Boolean)
      if (names.length) {
        lines.push('')
        lines.push(`> 来源：${names.join('、')}`)
      }
    }
    lines.push('')
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${conversation.value.title || '对话'}.md`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
  toast.success('对话已导出为 Markdown 文件')
}

// 引用分数展示（缺 score 时显示空，避免 NaN%）
const formatScore = (score?: number) => (score == null ? '' : `${Math.round(score * 100)}%`)

const submitPositiveFeedback = async (message: Message) => {
  try {
    await saveAnswerFeedback({ messageId: message.id, rating: 'UP' })
    feedbackByMessage.value[message.id] = 'UP'
    toast.success('已记录，这会帮助持续改进回答质量')
  } catch {
    toast.error('反馈提交失败')
  }
}

const openNegativeFeedback = (message: Message) => {
  feedbackMessage.value = message
  feedbackReason.value = ''
  expectedAnswer.value = ''
  feedbackDialogOpen.value = true
}

const submitNegativeFeedback = async () => {
  if (!feedbackMessage.value) return
  feedbackSaving.value = true
  try {
    await saveAnswerFeedback({
      messageId: feedbackMessage.value.id,
      rating: 'DOWN',
      reason: feedbackReason.value.trim() || undefined,
      expectedAnswer: expectedAnswer.value.trim() || undefined,
    })
    feedbackByMessage.value[feedbackMessage.value.id] = 'DOWN'
    feedbackDialogOpen.value = false
    toast.success(expectedAnswer.value.trim() ? '已加入回归评测集' : '已记录问题反馈')
  } catch {
    toast.error('反馈提交失败')
  } finally {
    feedbackSaving.value = false
  }
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
const cancelOngoingRequests = async () => {
  const controller = abortController
  await cancelRemoteStream()
  controller?.abort()
  abortController = null
  streamingMessageId.value = null
  sending.value = false
}

// 组件卸载时取消请求
onUnmounted(() => {
  cancelOngoingRequests()
})

// 路由离开时取消请求
onBeforeRouteLeave(() => {
  return cancelOngoingRequests()
})

onMounted(() => {
  loadConversation()
  loadMessages()
})
</script>

<template>
  <div class="chat-height flex flex-col">
    <!-- 头部 -->
    <div class="flex items-center gap-4 border-b pb-4">
      <Button variant="ghost" size="icon" @click="goBack">
        <ArrowLeft class="h-5 w-5" />
      </Button>
      <div class="min-w-0 flex-1">
        <h2 class="truncate text-lg font-semibold">{{ conversation?.title || '对话' }}</h2>
        <p class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-muted-foreground">
          <span>{{ conversation ? formatDateTime(conversation.createdAt) : '' }}</span>
          <span
            v-if="conversation?.knowledgeBaseName"
            class="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] text-primary"
          >
            <BookOpen class="h-3 w-3" />
            {{ conversation.knowledgeBaseName }}
          </span>
          <span
            v-if="conversation?.promptTemplateName"
            class="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px]"
          >
            {{ conversation.promptTemplateName }}
          </span>
        </p>
      </div>
      <Button
        variant="ghost"
        size="icon"
        class="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
        :disabled="!conversation"
        title="重命名对话"
        aria-label="重命名对话"
        @click="openRenameDialog"
      >
        <Pencil class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        class="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
        :disabled="!conversation || !messages.length"
        title="清空对话消息"
        aria-label="清空对话消息"
        @click="clearDialogOpen = true"
      >
        <Eraser class="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="sm"
        class="shrink-0 gap-1.5"
        :disabled="!messages.length"
        title="将当前对话导出为 Markdown 文件"
        @click="exportConversation"
      >
        <Download class="h-3.5 w-3.5" />
        导出
      </Button>
    </div>

    <!-- 消息区域 -->
    <div
      ref="messagesContainer"
      class="flex-1 overflow-auto p-4 space-y-4"
    >
      <div v-if="loading" class="flex justify-center py-8">
        <LoadingSkeleton type="card" :count="3" class="w-full" />
      </div>
      <div v-else-if="messages.length === 0" class="flex flex-col items-center justify-center py-10 text-center">
        <Bot class="mx-auto h-12 w-12 text-muted-foreground" />
        <p class="mt-4 text-muted-foreground">开始与 AI 对话吧</p>
        <p class="mt-1 text-xs text-muted-foreground/70">可以试试下面的问题，或直接输入你的问题</p>
        <div class="mt-5 flex max-w-xl flex-wrap items-center justify-center gap-2">
          <button
            v-for="prompt in examplePrompts"
            :key="prompt"
            type="button"
            class="rounded-full border border-border bg-muted/40 px-3.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
            @click="fillExamplePrompt(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </div>
      <template v-else>
        <!-- 工具调用审批确认卡片（write_note 等写工具） -->
        <div
          v-if="approvalPrompt"
          class="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4"
        >
          <div class="flex items-start gap-3">
            <Pencil class="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium text-amber-600">需要你的确认</p>
              <p class="mt-1 text-sm text-foreground">
                Agent 请求{{ approvalPrompt.toolName === 'write_note' ? '把内容整理成笔记保存到知识库' : `调用工具 ${approvalPrompt.toolName}` }}，是否允许执行？
              </p>
              <p v-if="approvalPrompt.argumentsSummary" class="mt-1 line-clamp-3 text-xs text-muted-foreground">
                {{ approvalPrompt.argumentsSummary }}
              </p>
              <div class="mt-3 flex items-center gap-2">
                <Button size="sm" variant="default" :disabled="approvalBusy" @click="handleApprovalDecision('approved')">
                  <Check class="mr-1 h-4 w-4" /> 同意执行
                </Button>
                <Button size="sm" variant="outline" :disabled="approvalBusy" @click="handleApprovalDecision('denied')">
                  <X class="mr-1 h-4 w-4" /> 拒绝
                </Button>
                <Loader2 v-if="approvalBusy" class="ml-1 h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            </div>
          </div>
        </div>
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
                      @click="copyMessage(message)"
                    >
                      <Copy class="h-3.5 w-3.5" />
                    </Button>
                    <template v-if="message.role === 'assistant' && message.id > 0 && !isErrorMessage(message) && !streamingMessageId">
                      <Button
                        variant="ghost"
                        size="icon"
                        class="h-7 w-7 text-muted-foreground hover:text-primary"
                        title="重新生成回答"
                        @click="regenerateMessage(message)"
                      >
                        <RefreshCw class="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="h-7 w-7"
                        :class="feedbackByMessage[message.id] === 'UP' ? 'text-emerald-400' : 'text-muted-foreground'"
                        title="回答有帮助"
                        @click="submitPositiveFeedback(message)"
                      >
                        <ThumbsUp class="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="h-7 w-7"
                        :class="feedbackByMessage[message.id] === 'DOWN' ? 'text-rose-400' : 'text-muted-foreground'"
                        title="回答需要改进"
                        @click="openNegativeFeedback(message)"
                      >
                        <ThumbsDown class="h-3.5 w-3.5" />
                      </Button>
                    </template>
                    <!-- 重试按钮（仅在错误消息上显示） -->
                    <Button
                      v-if="isErrorMessage(message) && !streamingMessageId"
                      variant="ghost"
                      size="sm"
                      class="h-6 px-2 text-xs"
                      @click="handleRetryMessage(message)"
                    >
                      <RefreshCw class="h-3 w-3 mr-1" />
                      重试
                    </Button>
                  </div>
                </div>
              </template>

              <!-- 知识来源（流式输出期间与完成后都会显示） -->
              <div v-if="message.role === 'assistant' && message.sources && message.sources.length > 0" class="mt-3 pt-3 border-t border-secondary-foreground/20">
                <p class="text-xs font-medium mb-2 flex items-center gap-1">
                  <span>📚</span>
                  <span>知识来源</span>
                  <span class="opacity-60">({{ message.sources.length }}条)</span>
                </p>
                <div class="space-y-1.5">
                  <template v-for="(source, index) in message.sources" :key="index">
                    <router-link
                      v-if="conversation?.knowledgeBaseId && source.document_id"
                      :to="`/knowledge-base/${conversation.knowledgeBaseId}/chunks/${source.document_id}`"
                      class="block text-xs bg-secondary-foreground/5 rounded px-2 py-1.5 transition-colors hover:bg-primary/10"
                      :title="'查看分块：' + (source.document_name || source.title || `文档 #${source.document_id ?? '未知'}`)"
                    >
                      <div class="flex items-center justify-between gap-2">
                        <span class="font-medium truncate flex-1" :title="source.document_name || source.title">
                          {{ source.document_name || source.title || `文档 #${source.document_id ?? '未知'}` }}
                        </span>
                        <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                          {{ formatScore(source.score) }}
                        </span>
                      </div>
                      <p v-if="source.outline_path && source.outline_path.length" class="mt-1 text-[10px] opacity-60 truncate">
                        {{ source.outline_path.join(' > ') }}
                      </p>
                      <p v-if="source.content" class="mt-1 text-[11px] opacity-60 line-clamp-2">
                        {{ source.content }}
                      </p>
                    </router-link>
                    <div
                      v-else
                      class="text-xs bg-secondary-foreground/5 rounded px-2 py-1.5"
                    >
                      <div class="flex items-center justify-between gap-2">
                        <span class="font-medium truncate flex-1" :title="source.document_name || source.title">
                          {{ source.document_name || source.title || `文档 #${source.document_id ?? '未知'}` }}
                        </span>
                        <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                          {{ formatScore(source.score) }}
                        </span>
                      </div>
                      <p v-if="source.outline_path && source.outline_path.length" class="mt-1 text-[10px] opacity-60 truncate">
                        {{ source.outline_path.join(' > ') }}
                      </p>
                      <p v-if="source.content" class="mt-1 text-[11px] opacity-60 line-clamp-2">
                        {{ source.content }}
                      </p>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 输入区域 -->
    <div class="border-t pt-4">
      <div class="flex gap-2">
        <Input
          id="chat-input"
          v-model="inputMessage"
          placeholder="输入消息...（Enter 发送，Shift+Enter 换行）"
          :disabled="sending"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @keyup.enter="!isComposing && handleSend()"
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

    <Dialog v-model:open="renameDialogOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>重命名对话</DialogTitle>
          <DialogDescription>修改后列表与头部会立即更新。</DialogDescription>
        </DialogHeader>
        <div class="space-y-2">
          <Label for="rename-title">对话名称</Label>
          <Input
            id="rename-title"
            v-model="renameTitle"
            maxlength="100"
            placeholder="请输入新的对话名称"
            @keydown.enter="submitRename"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="renameDialogOpen = false">取消</Button>
          <Button @click="submitRename">保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="clearDialogOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>清空对话？</DialogTitle>
          <DialogDescription>将删除「{{ conversation?.title }}」中的全部消息，对话本身会保留。此操作不可恢复。</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="clearDialogOpen = false">取消</Button>
          <Button variant="destructive" @click="submitClear">清空消息</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="feedbackDialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>告诉我们哪里需要改进</DialogTitle>
          <DialogDescription>填写期望答案后，这条问题会自动进入回归评测集。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <label class="text-sm font-medium" for="feedback-reason">问题原因</label>
            <textarea
              id="feedback-reason"
              v-model="feedbackReason"
              rows="3"
              maxlength="500"
              class="block w-full resize-y rounded-lg border border-input bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
              placeholder="例如：没有回答问题重点、引用不准确"
            />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium" for="expected-answer">期望答案（可选）</label>
            <textarea
              id="expected-answer"
              v-model="expectedAnswer"
              rows="5"
              maxlength="10000"
              class="block w-full resize-y rounded-lg border border-input bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
              placeholder="输入可作为回归测试基准的答案"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="feedbackDialogOpen = false">取消</Button>
          <Button :disabled="feedbackSaving" @click="submitNegativeFeedback">
            {{ feedbackSaving ? '提交中...' : '提交反馈' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
/* 移动端软键盘弹出时，dvh 能跟随可视高度收缩，避免输入框被遮挡 */
.chat-height {
  height: calc(100vh - 8rem);
}
@supports (height: 100dvh) {
  .chat-height {
    height: calc(100dvh - 8rem);
  }
}
</style>
