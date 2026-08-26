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
import * as voiceApi from '@/api/voice'
import { ArrowLeft, BookOpen, Check, Copy, Download, Eraser, Image as ImageIcon, Mic, Pencil, Send, User, Bot, Loader2, Square, RefreshCw, ThumbsUp, ThumbsDown, Volume2, X } from 'lucide-vue-next'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'
import { formatDateTime, formatTime, parseServerTime } from '@/utils/date'
import { friendlyErrorMessage } from '@/utils/errorMessage'
import { SseDataParser, type SseDataEvent } from '@/utils/sse'
import {
  CHAT_APPROVAL_CHECK_INTERVAL_MS,
  CHAT_RELOAD_DELAY_MS,
  CHAT_RETRY_DELAY_MS,
} from '@/constants/timing'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useChatSending } from '@/composables/useChatSending'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const toast = useToast()
const { t } = useI18n()

const conversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const feedbackByMessage = ref<Record<number, 'UP' | 'DOWN'>>({})
const feedbackDialogOpen = ref(false)
const feedbackMessage = ref<Message | null>(null)
const feedbackReason = ref('')
const expectedAnswer = ref('')
const feedbackSaving = ref(false)
const loading = ref(false)
// 发送单飞状态机（R16-18）：sending 置位/复位收口到 runExclusive/forceIdle，
// 消灭"先复位再发送"手工时序（第三十六批 retry/regenerate 数据丢失的缺陷模式）
const { sending, runExclusive, forceIdle } = useChatSending()
const inputMessage = ref('')
const isComposing = ref(false) // 中文输入法组合态：组合期间按 Enter 不发送

// 对话图片输入（实验特性）：url = 服务端相对地址（随消息发送/持久化），
// preview = 本地 objectURL（即时预览；随气泡展示，页面卸载时由浏览器回收）
const pendingImages = ref<Array<{ url: string; preview: string }>>([])
const imageInputRef = ref<HTMLInputElement | null>(null)
const uploadingImage = ref(false)

const triggerImagePick = () => imageInputRef.value?.click()

const onImagesChosen = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  const allowed = ['image/jpeg', 'image/png', 'image/webp']
  for (const f of files) {
    if (!allowed.includes(f.type)) {
      alert('仅支持 JPG / PNG / WEBP 图片')
      continue
    }
    if (f.size > 5 * 1024 * 1024) {
      alert('单张图片不能超过5MB')
      continue
    }
    if (pendingImages.value.length >= 4) {
      alert('每次最多携带4张图片')
      break
    }
    uploadingImage.value = true
    try {
      const res = await conversationApi.uploadChatImage(f)
      pendingImages.value.push({ url: res.data.url, preview: URL.createObjectURL(f) })
    } catch (err) {
      console.error('图片上传失败:', err)
      alert('图片上传失败，请重试')
    } finally {
      uploadingImage.value = false
    }
  }
}

const removePendingImage = (i: number) => {
  const [removed] = pendingImages.value.splice(i, 1)
  if (removed) URL.revokeObjectURL(removed.preview)
}

// ── 语音输入/播报（Batch 10：VOICE_ENABLED 默认关闭，按钮按 /voice/status 渲染）──
const voiceStatus = ref<voiceApi.VoiceStatus>({ enabled: false, stt: false, tts: false })
const recording = ref(false)
const transcribing = ref(false)
const speakingMessageId = ref<string | null>(null)
let mediaRecorder: MediaRecorder | null = null
let recordedChunks: Blob[] = []
let currentAudio: HTMLAudioElement | null = null

onMounted(async () => {
  try {
    const result = await voiceApi.getVoiceStatus()
    if (result.data) voiceStatus.value = result.data
  } catch {
    /* 语音状态获取失败视作未启用 */
  }
})

const toggleRecording = async () => {
  if (recording.value) {
    mediaRecorder?.stop()
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    recordedChunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data)
    }
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop())
      recording.value = false
      if (!recordedChunks.length) return
      const blob = new Blob(recordedChunks, { type: 'audio/webm' })
      transcribing.value = true
      try {
        const text = await voiceApi.transcribeAudio(blob, 'audio.webm', navigator.language)
        if (text) inputMessage.value = inputMessage.value ? `${inputMessage.value} ${text}` : text
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '语音识别失败')
      } finally {
        transcribing.value = false
      }
    }
    recording.value = true
    mediaRecorder.start()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '无法访问麦克风')
    recording.value = false
  }
}

let currentAudioUrl: string | null = null

const releaseCurrentAudio = () => {
  try {
    currentAudio?.pause()
    if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl)
  } catch { /* 忽略 */ }
  currentAudio = null
  currentAudioUrl = null
}

const speakMessage = async (messageId: string, content: string) => {
  if (speakingMessageId.value === messageId) {
    releaseCurrentAudio()
    speakingMessageId.value = null
    return
  }
  releaseCurrentAudio() // 切换播报时释放上一个音频 blob URL（泄漏修复）
  try {
    const audioUrl = await voiceApi.synthesizeSpeech(content)
    currentAudio = new Audio(audioUrl)
    currentAudioUrl = audioUrl
    speakingMessageId.value = messageId
    currentAudio.onended = () => {
      speakingMessageId.value = null
      URL.revokeObjectURL(audioUrl)
    }
    await currentAudio.play()
  } catch (error) {
    releaseCurrentAudio()
    speakingMessageId.value = null
    toast.error(error instanceof Error ? error.message : '语音播报失败')
  }
}
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
      // Safari 不支持 'yyyy-MM-dd HH:mm:ss' 构造——用项目统一的手动解析
      const created = parseServerTime(a.createdAt)?.getTime()
      return created != null && now - created < 3 * 60 * 1000 // 最近 3 分钟
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
      setTimeout(() => loadMessages(true), CHAT_RELOAD_DELAY_MS)
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
    // 对话图片输入：服务端存相对 URL，<img> 无法带登录态——统一转 objectURL
    for (const m of res.data) {
      if (m.role === 'user' && m.images?.length) {
        m.images = await Promise.all(
          m.images.map(u => conversationApi.fetchChatImageBlobUrl(u).catch(() => u)),
        )
      }
    }
    messages.value = res.data
    try {
      const feedback = await getAnswerFeedback(id)
      feedbackByMessage.value = Object.fromEntries(
        feedback.data.map(item => [item.messageId, item.rating]),
      )
    } catch {
      feedbackByMessage.value = {}
    }
    const stickNow = () => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    }
    if (silent) {
      await nextTick()
      await nextTick()
      stickNow()
    } else {
      await scrollToBottom()
    }
    // Markdown 与图片为异步渲染，容器高度在首帧滚动后仍会增长——
    // 二次/三次校正，确保「点进会话即定位到最新消息」而不是停在顶部
    setTimeout(stickNow, 200)
    setTimeout(stickNow, 600)
  } catch (error) {
    console.error('加载消息失败:', error)
  } finally {
    if (!silent) loading.value = false
  }
}

// 发送主流程（无守卫版）：输入来自输入框与待发图片队列。
// retry/regenerate 复用本流程重发旧提问；单飞守卫统一由 runExclusive 承接。
const runSendFlow = async () => {
  if (!inputMessage.value.trim() && pendingImages.value.length === 0) return

  const content = inputMessage.value.trim()
  inputMessage.value = ''
  const imageUrls = pendingImages.value.map(p => p.url)
  const imagePreviews = pendingImages.value.map(p => p.preview)

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
      images: imagePreviews.length ? imagePreviews : undefined,
      createdAt: timeStr,
    }
    messages.value.push(userMessage)
    // 预览 objectURL 已挂到气泡上——不 revoke，页面卸载时由浏览器统一回收
    pendingImages.value = []
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
    // R15-29：断线自动重试——尚未收到任何内容且错误是网络类（fetch 在
    // 连接建立/传输中断开抛 TypeError）时，用同一 requestId 重发（后端
    // 按 requestId 幂等，不会产生重复消息）；已有内容时保持既有
    // 「回复中断，请重试」语义，避免部分内容重复拼接。
    let response: Response | null = null
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        response = await fetch('/api/conversation/message/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'satoken': userStore.token || '',
          },
          body: JSON.stringify({
            conversationId: Number(route.params.id),
            content,
            requestId,
            images: imageUrls.length ? imageUrls : undefined,
            // KB 会话启用写能力：模型可见 write_note（写工具），调用前会请求人工审批
            capabilityProfile: conversation.value?.knowledgeBaseId ? 'approval_write' : undefined,
          }),
          signal: abortController.signal,
        })
        break
      } catch (err) {
        const isNetworkError = err instanceof TypeError || (err instanceof Error && err.name === 'TypeError')
        if (isNetworkError && attempt < 1 && !abortController.signal.aborted) {
          await new Promise(r => setTimeout(r, CHAT_RETRY_DELAY_MS))
          continue
        }
        throw err
      }
    }
    if (!response) {
      throw new Error('Stream request failed')
    }

    if (response.status === 401) {
      // M9: 聊天流绕过 axios 拦截器 — 401 接入统一登出，避免两种登出体验割裂
      const { handleUnauthorized401 } = await import('@/api/request')
      throw handleUnauthorized401('登录已过期')
    }

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
          // 流式重试协议：content_reset 清空当前气泡（groundedness 重试替换语义）
          if (parsed.content_reset === true) {
            const resetMsg = messages.value.find(m => m.id === pendingId)
            if (resetMsg) resetMsg.content = ''
            return
          }
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

  } catch (error) {
    // 如果是用户取消，不显示错误
    const errorName = error instanceof Error ? error.name : ''
    if (errorName === 'AbortError') {
      const index = pendingId === null ? -1 : messages.value.findIndex(m => m.id === pendingId)
      if (index !== -1 && !messages.value[index].content) {
        messages.value.splice(index, 1)
      }
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
        images: imageUrls.length ? imageUrls : undefined,
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
    // sending 复位由 runExclusive 的 finally 承接（R16-18）
    streamingMessageId.value = null
    abortController = null
    if (activeRequestId === requestId) {
      activeRequestId = null
    }
    // 工具调用可能已产生待审批（如 write_note），延迟检查并弹出确认卡片
    setTimeout(maybeCheckApproval, CHAT_APPROVAL_CHECK_INTERVAL_MS)
  }
}

const handleSend = async () => {
  if (isComposing.value) return
  // 空内容/组合态以外的守卫（双击、并发发送）统一走单飞状态机
  await runExclusive(runSendFlow)
}

const scrollToBottom = async () => {
  await nextTick()
  await nextTick()
  // R15-29：用 rAF 等待下一帧渲染完成，替代固定 100ms sleep——
  // 帧率正常时更快、渲染被节流（后台标签页）时也不会提前滚动
  await new Promise(resolve => requestAnimationFrame(() => resolve(null)))
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 仅当视口本就贴近底部时才贴底——图片等异步资源加载完成时高度增长，
// 不把主动上翻阅读历史 long 内容的用户拽回底部
const stickIfNearBottom = () => {
  const el = messagesContainer.value
  if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) {
    el.scrollTop = el.scrollHeight
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
  // 强制释放单飞守卫（在途发送的收尾不再维持占用，行为与旧实现一致）
  forceIdle()
}

// 重试消息（先在服务端删除失败轮次，避免重复）
const handleRetryMessage = async (message: Message) => {
  // 单飞守卫跨越"删除在途 + 重发"全程：双击/并发由 runExclusive 拒绝，
  // 不再依赖手工置位/复位的时序约定（R16-18）
  await runExclusive(async () => {
    // 找到这条消息的前一条用户消息
    const messageIndex = messages.value.findIndex(m => m.id === message.id)
    if (messageIndex <= 0) return

    const userMessage = messages.value[messageIndex - 1]
    if (!userMessage || userMessage.role !== 'user') return

    // 对话图片输入：把原消息图片恢复为待发送状态（blob/相对地址均可重上传）
    try {
      for (const u of userMessage.images || []) {
        try {
          const blob = await (await fetch(u)).blob()
          const res = await conversationApi.uploadChatImage(
            new File([blob], 'retry.png', { type: blob.type || 'image/png' }))
          pendingImages.value.push({ url: res.data.url, preview: u })
        } catch { /* 单图恢复失败忽略 */ }
      }
    } catch { /* 忽略恢复失败 */ }

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
    // 移除用户消息（因为发送流程会重新添加）
    messages.value.splice(messageIndex - 1, 1)
    await runSendFlow()
  })
}

// 重新生成：服务端删除旧问答对后重新发送提问（不产生重复轮次）
const regenerateMessage = async (message: Message) => {
  await runExclusive(async () => {
    const messageIndex = messages.value.findIndex(m => m.id === message.id)
    if (messageIndex <= 0) return

    const userMessage = messages.value[messageIndex - 1]
    if (!userMessage || userMessage.role !== 'user') return

    try {
      for (const u of userMessage.images || []) {
        try {
          const blob = await (await fetch(u)).blob()
          const res = await conversationApi.uploadChatImage(
            new File([blob], 'retry.png', { type: blob.type || 'image/png' }))
          pendingImages.value.push({ url: res.data.url, preview: u })
        } catch { /* 单图恢复失败忽略 */ }
      }
    } catch { /* 忽略恢复失败 */ }

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
    await runSendFlow()
  })
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
  forceIdle()
}

// 组件卸载时取消请求
onUnmounted(() => {
  cancelOngoingRequests()
  // 离开页面：停止录音（麦克风释放）并暂停语音播报
  try { mediaRecorder?.stop() } catch { /* 未在录音 */ }
  releaseCurrentAudio()
})

// 路由离开时取消请求
onBeforeRouteLeave(() => {
  return cancelOngoingRequests()
})

onMounted(() => {
  loadConversation()
  loadMessages()
  // 支持从列表页示例问题带入（/chat/:id?q=...）
  const initialQuestion = route.query.q
  if (initialQuestion) {
    inputMessage.value = String(initialQuestion)
    router.replace({ query: { ...route.query, q: undefined } })
  }
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
                  <div v-if="message.images?.length" class="mb-1 flex flex-wrap gap-1.5">
                    <img
                      v-for="(src, i) in message.images"
                      :key="i"
                      :src="src"
                      class="max-h-36 rounded border border-background/20"
                      alt="用户上传的图片"
                      @load="stickIfNearBottom"
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
                      @click="copyMessage(message)"
                    >
                      <Copy class="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      v-if="voiceStatus.tts && message.id > 0 && message.content && !isErrorMessage(message)"
                      variant="ghost"
                      size="icon"
                      class="h-7 w-7 text-muted-foreground hover:text-primary"
                      :title="speakingMessageId === String(message.id) ? '停止播报' : '语音播报'"
                      @click="speakMessage(String(message.id), message.content)"
                    >
                      <Volume2 v-if="speakingMessageId !== String(message.id)" class="h-3.5 w-3.5" />
                      <Square v-else class="h-3.5 w-3.5" />
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
      <!-- 对话图片输入（实验特性）：待发送图片预览 -->
      <div v-if="pendingImages.length" class="mb-2 flex flex-wrap gap-2">
        <div v-for="(img, i) in pendingImages" :key="img.url" class="relative">
          <img :src="img.preview" class="h-16 w-16 rounded border object-cover" alt="待发送图片" />
          <button
            class="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-xs leading-none text-destructive-foreground"
            title="移除"
            @click="removePendingImage(i)"
          >
            ×
          </button>
        </div>
      </div>
      <div class="flex gap-2">
        <input
          ref="imageInputRef"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          class="hidden"
          @change="onImagesChosen"
        />
        <Button
          variant="outline"
          :disabled="sending || uploadingImage"
          :title="t('chat.addImage')"
          @click="triggerImagePick"
        >
          <Loader2 v-if="uploadingImage" class="mr-2 h-4 w-4 animate-spin" />
          <ImageIcon v-else class="h-4 w-4" />
        </Button>
        <Input
          id="chat-input"
          v-model="inputMessage"
          :placeholder="t('chat.inputPlaceholder')"
          :disabled="sending"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @keyup.enter="!isComposing && handleSend()"
        />
        <!-- 语音输入按钮（Batch 10：STT 启用时渲染） -->
        <Button
          v-if="voiceStatus.stt"
          variant="outline"
          :disabled="sending"
          :class="recording ? 'text-rose-500 border-rose-400' : ''"
          :title="recording ? t('chat.stopRecording') : t('chat.voiceInput')"
          @click="toggleRecording"
        >
          <Loader2 v-if="transcribing" class="h-4 w-4 mr-2 animate-spin" />
          <Mic v-else class="h-4 w-4" :class="recording ? 'animate-pulse' : ''" />
          {{ recording ? t('chat.stop') : t('chat.voice') }}
        </Button>
        <!-- 停止生成按钮 -->
        <Button
          v-if="sending"
          variant="destructive"
          @click="handleStopGeneration"
        >
          <Square class="h-4 w-4 mr-2" />
          {{ t('chat.stopGenerating') }}
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
