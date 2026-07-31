import service, { del, get, post, put, upload } from './request'
import type {
  ApiResponse,
  PageResult,
  Conversation,
  Message,
  ConversationCreateDTO,
  MessageSendDTO
} from './types'

// 创建对话
export const createConversation = (data: ConversationCreateDTO): Promise<ApiResponse<Conversation>> => {
  return post('/conversation', data)
}

// 删除对话
export const deleteConversation = (id: number): Promise<ApiResponse<void>> => {
  return del(`/conversation/${id}`)
}

// 重命名对话
export const renameConversation = (id: number, title: string): Promise<ApiResponse<void>> => {
  return put(`/conversation/${id}`, { title })
}

// 清空对话消息（保留对话）
export const clearConversationMessages = (id: number): Promise<ApiResponse<void>> => {
  return del(`/conversation/${id}/messages`)
}

// 删除单条消息（重新生成/重试去重用）
export const deleteConversationMessage = (conversationId: number, messageId: number): Promise<ApiResponse<void>> => {
  return del(`/conversation/${conversationId}/messages/${messageId}`)
}

// 获取对话详情
export const getConversation = (id: number): Promise<ApiResponse<Conversation>> => {
  return get(`/conversation/${id}`)
}

// 分页查询对话列表
export const getConversationList = (params: {
  page: number
  pageSize: number
}): Promise<ApiResponse<PageResult<Conversation>>> => {
  return get('/conversation/list', params)
}

// 获取当前用户的对话列表（支持后端模糊搜索标题与按知识库筛选）
export const getMyConversations = (params?: {
  page?: number
  pageSize?: number
  title?: string
  knowledgeBaseId?: number
}): Promise<ApiResponse<PageResult<Conversation>>> => {
  return get('/conversation/my', params)
}

// 发送消息
export const sendMessage = (data: MessageSendDTO): Promise<ApiResponse<Message>> => {
  return post('/conversation/message', data)
}

// 获取对话消息列表
export const getConversationMessages = (conversationId: number): Promise<ApiResponse<Message[]>> => {
  return get(`/conversation/${conversationId}/messages`)
}

// 取消正在生成的流式消息，并让后端保存已生成的部分内容
// 上传对话图片（对话图片输入，实验特性）：返回相对 URL，发送消息时放入 images
export const uploadChatImage = (file: File): Promise<ApiResponse<{ url: string }>> => {
  const form = new FormData()
  form.append('file', file)
  return upload('/conversation/chat-image', form)
}

// 以登录态拉取对话图片并转 objectURL（<img> 无法携带 satoken 头，与头像同模式）
export const fetchChatImageBlobUrl = async (url: string): Promise<string> => {
  const blob = await service.get(url, { responseType: 'blob' })
  return URL.createObjectURL(blob as unknown as Blob)
}

export const cancelStream = (requestId: string): Promise<ApiResponse<boolean>> => {
  return post('/conversation/message/stream/cancel', { requestId })
}
