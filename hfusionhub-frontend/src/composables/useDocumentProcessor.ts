import { ref, onBeforeUnmount } from 'vue'
import * as vectorizationApi from '@/api/vectorization'
import type { Document } from '@/api/types'
import { DOCUMENT_PARSE_POLL_INTERVAL_MS } from '@/constants/timing'

export interface ProcessingStatus {
  status?: string
  message?: string
  stage?: string
  progress?: number
  elapsedSeconds?: number
  estimatedSeconds?: number
  remainingSeconds?: number
  processedChunks?: number
  totalChunks?: number
  chunksCount?: number
}

/**
 * 文档处理相关的组合式函数
 * 包含模型加载、状态轮询、处理状态管理等复用逻辑
 */
export function useDocumentProcessor() {
  // 处理中的文档ID集合
  const processingDocs = ref<Set<number>>(new Set())
  const processingStatus = ref<Record<number, ProcessingStatus>>({})
  const activePollingDocs = new Set<number>()

  // 轮询定时器集合
  const pollingTimers = new Set<ReturnType<typeof setTimeout>>()

  // 模型选择相关
  const isModelDialogOpen = ref(false)
  const selectedDocForVectorize = ref<Document | null>(null)
  const availableModels = ref<Array<{ id: string; name: string; type: string; dimension: number; description?: string }>>([])
  const selectedModel = ref('ollama')
  const loadingModels = ref(false)

  /**
   * 添加文档到处理中状态
   */
  const addProcessing = (id: number) => {
    const s = new Set(processingDocs.value)
    s.add(id)
    processingDocs.value = s
  }

  /**
   * 从处理中状态移除文档
   */
  const removeProcessing = (id: number) => {
    const s = new Set(processingDocs.value)
    s.delete(id)
    processingDocs.value = s
  }

  const toNumber = (value: unknown): number | undefined => {
    if (value === null || value === undefined || value === '') return undefined
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }

  const normalizeStatus = (payload: any): ProcessingStatus => ({
    status: payload?.status,
    message: payload?.message,
    stage: payload?.stage,
    progress: toNumber(payload?.progress),
    elapsedSeconds: toNumber(payload?.elapsed_seconds),
    estimatedSeconds: toNumber(payload?.estimated_seconds),
    remainingSeconds: toNumber(payload?.remaining_seconds),
    processedChunks: toNumber(payload?.processed_chunks),
    totalChunks: toNumber(payload?.total_chunks),
    chunksCount: toNumber(payload?.chunks_count),
  })

  const parseStatusPayload = (rawStatus: any) => {
    if (typeof rawStatus === 'string') {
      try {
        return JSON.parse(rawStatus)
      } catch {
        console.warn('Failed to parse status payload JSON, using raw value')
        return { status: 'UNKNOWN', message: String(rawStatus).slice(0, 200) }
      }
    }
    return rawStatus
  }

  const updateProcessingStatus = (id: number, payload: any) => {
    processingStatus.value = {
      ...processingStatus.value,
      [id]: normalizeStatus(payload),
    }
  }

  const clearProcessingStatus = (id: number) => {
    const next = { ...processingStatus.value }
    delete next[id]
    processingStatus.value = next
  }

  const processingProgress = (id: number) => {
    const progress = processingStatus.value[id]?.progress ?? 5
    return Math.max(0, Math.min(100, Math.round(progress)))
  }

  const formatProcessingTime = (seconds?: number | null) => {
    if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '计算中'
    const total = Math.max(0, Math.round(seconds))
    if (total < 60) return `${total}秒`
    const minutes = Math.floor(total / 60)
    const restSeconds = total % 60
    if (minutes < 60) return restSeconds > 0 ? `${minutes}分${restSeconds}秒` : `${minutes}分钟`
    const hours = Math.floor(minutes / 60)
    const restMinutes = minutes % 60
    return restMinutes > 0 ? `${hours}小时${restMinutes}分钟` : `${hours}小时`
  }

  const getStageText = (stage?: string) => {
    const stageMap: Record<string, string> = {
      queued: '排队中',
      parsing: '解析文档',
      chunking: '生成分块',
      embedding: '生成向量',
      storing: '写入索引',
      callback: '同步状态',
      completed: '已完成',
      failed: '处理失败',
    }
    return stageMap[stage || 'queued'] || '处理中'
  }

  /**
   * 加载可用模型列表
   */
  const loadModels = async () => {
    loadingModels.value = true
    try {
      const res = await vectorizationApi.getAvailableModels()
      availableModels.value = res.data.models || []
      // 默认选择第一个模型
      if (availableModels.value.length > 0) {
        selectedModel.value = availableModels.value[0].id
      }
    } catch (error) {
      console.error('加载模型列表失败:', error)
      // 使用默认模型列表
      availableModels.value = [
        { id: 'ollama', name: 'Ollama - bge-m3:latest', type: 'local', dimension: 1024, description: '本地 Ollama 嵌入模型 (BGE-M3)' }
      ]
    } finally {
      loadingModels.value = false
    }
  }

  /**
   * 打开模型选择对话框
   */
  const openModelDialog = (doc: Document) => {
    selectedDocForVectorize.value = doc
    isModelDialogOpen.value = true
    loadModels()
  }

  /**
   * 轮询文档处理状态
   * @param docId 文档ID
   * @param onStatusChange 状态变更回调
   * @param maxAttempts 最大轮询次数（默认60次，每次2秒，共2分钟）
   */
  const pollDocumentStatus = async (
    docId: number,
    onStatusChange?: () => void,
    maxAttempts = 600
  ) => {
    if (activePollingDocs.has(docId)) {
      return
    }
    activePollingDocs.add(docId)
    let attempts = 0

    const checkStatus = async () => {
      if (attempts >= maxAttempts) {
        removeProcessing(docId)
        activePollingDocs.delete(docId)
        return
      }

      try {
        const res = await vectorizationApi.getVectorizationStatus(docId)
        const payload = parseStatusPayload(res.data)
        updateProcessingStatus(docId, payload)
        const status = payload?.status

        // SUPERSEDED：重处理触发的取代终态，同样停止轮询并清理（此前缺失导致被取代文档永久轮询）
        if (status === 'COMPLETED' || status === 'FAILED' || status === 'SUPERSEDED' || status === 'NOT_FOUND' || status === 'ERROR') {
          // 完成或失败，停止轮询
          removeProcessing(docId)
          activePollingDocs.delete(docId)
          if (status === 'COMPLETED' || status === 'SUPERSEDED' || status === 'NOT_FOUND') {
            clearProcessingStatus(docId)
          }
          onStatusChange?.()
          return
        }

        attempts++
        const timer = setTimeout(checkStatus, DOCUMENT_PARSE_POLL_INTERVAL_MS)
        pollingTimers.add(timer)
      } catch (error) {
        console.error('查询状态失败:', error)
        removeProcessing(docId)
        clearProcessingStatus(docId)
        activePollingDocs.delete(docId)
        onStatusChange?.()
      }
    }

    checkStatus()
  }

  /**
   * 启动文档向量化
   */
  const startVectorization = async (
    doc: Document,
    options?: {
      onSuccess?: () => void
      onError?: (error: any) => void
    }
  ) => {
    addProcessing(doc.id)
    updateProcessingStatus(doc.id, {
      status: 'PROCESSING',
      stage: 'queued',
      progress: 3,
      message: '已提交解析任务，正在估算处理时间',
    })
    isModelDialogOpen.value = false

    try {
      await vectorizationApi.startVectorization(doc.id, selectedModel.value)
      doc.status = 1
      pollDocumentStatus(doc.id, options?.onSuccess)
    } catch (error) {
      console.error('启动向量化失败:', error)
      removeProcessing(doc.id)
      clearProcessingStatus(doc.id)
      options?.onError?.(error)
      throw error
    }
  }

  const trackProcessingDocuments = (docs: Document[], onStatusChange?: () => void) => {
    docs.filter(doc => doc.status === 1).forEach(doc => {
      addProcessing(doc.id)
      if (!processingStatus.value[doc.id]) {
        updateProcessingStatus(doc.id, {
          status: 'PROCESSING',
          stage: 'queued',
          progress: 5,
          message: '正在同步解析进度',
        })
      }
      pollDocumentStatus(doc.id, onStatusChange)
    })
  }

  /**
   * 重置文档状态
   */
  const resetDocument = async (doc: Document) => {
    try {
      await vectorizationApi.resetDocument(doc.id)
      doc.status = 0
      doc.errorMessage = null
    } catch (error) {
      console.error('重置文档失败:', error)
      throw error
    }
  }

  /**
   * 清理所有轮询定时器
   */
  const clearAllTimers = () => {
    pollingTimers.forEach(timer => clearTimeout(timer))
    pollingTimers.clear()
    activePollingDocs.clear()
  }

  // 组件卸载时清理定时器
  onBeforeUnmount(() => {
    clearAllTimers()
  })

  return {
    // 状态
    processingDocs,
    processingStatus,
    isModelDialogOpen,
    selectedDocForVectorize,
    availableModels,
    selectedModel,
    loadingModels,

    // 方法
    addProcessing,
    removeProcessing,
    processingProgress,
    formatProcessingTime,
    getStageText,
    loadModels,
    openModelDialog,
    pollDocumentStatus,
    trackProcessingDocuments,
    startVectorization,
    resetDocument,
    clearAllTimers,
  }
}
