import { get, post, del } from './request'
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
export const cancelStream = (requestId: string): Promise<ApiResponse<boolean>> => {
  return post('/conversation/message/stream/cancel', { requestId })
}
