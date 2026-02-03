import { ref, onBeforeUnmount } from 'vue'
import * as vectorizationApi from '@/api/vectorization'
import type { Document } from '@/api/types'

/**
 * 文档处理相关的组合式函数
 * 包含模型加载、状态轮询、处理状态管理等复用逻辑
 */
export function useDocumentProcessor() {
  // 处理中的文档ID集合
  const processingDocs = ref<Set<number>>(new Set())

  // 轮询定时器集合
  const pollingTimers = new Set<ReturnType<typeof setTimeout>>()

  // 模型选择相关
  const isModelDialogOpen = ref(false)
  const selectedDocForVectorize = ref<Document | null>(null)
  const availableModels = ref<Array<{ id: string; name: string; type: string; dimension: number; description: string }>>([])
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
    maxAttempts = 60
  ) => {
    let attempts = 0

    const checkStatus = async () => {
      if (attempts >= maxAttempts) {
        removeProcessing(docId)
        return
      }

      try {
        const res = await vectorizationApi.getVectorizationStatus(docId)
        const status = res.data?.status

        if (status === 2 || status === 3) {
          // 完成或失败，停止轮询
          removeProcessing(docId)
          onStatusChange?.()
          return
        }

        attempts++
        const timer = setTimeout(checkStatus, 2000)
        pollingTimers.add(timer)
      } catch (error) {
        console.error('查询状态失败:', error)
        removeProcessing(docId)
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
    isModelDialogOpen.value = false

    try {
      await vectorizationApi.startVectorization(doc.id, selectedModel.value)
      doc.status = 1
      pollDocumentStatus(doc.id, options?.onSuccess)
      options?.onSuccess?.()
    } catch (error) {
      console.error('启动向量化失败:', error)
      removeProcessing(doc.id)
      options?.onError?.(error)
      throw error
    }
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
  }

  // 组件卸载时清理定时器
  onBeforeUnmount(() => {
    clearAllTimers()
  })

  return {
    // 状态
    processingDocs,
    isModelDialogOpen,
    selectedDocForVectorize,
    availableModels,
    selectedModel,
    loadingModels,

    // 方法
    addProcessing,
    removeProcessing,
    loadModels,
    openModelDialog,
    pollDocumentStatus,
    startVectorization,
    resetDocument,
    clearAllTimers,
  }
}
