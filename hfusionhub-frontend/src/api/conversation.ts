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
export const createConversation = (data: ConversationCreateDTO): Promise<ApiResponse<number>> => {
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
  pageNum: number
  pageSize: number
}): Promise<ApiResponse<PageResult<Conversation>>> => {
  return get('/conversation/list', params)
}

// 获取当前用户的对话列表
export const getMyConversations = (params?: {
  pageNum?: number
  pageSize?: number
}): Promise<ApiResponse<PageResult<Conversation>>> => {
  return get('/conversation/my', params)
}

// 发送消息
export const sendMessage = (data: MessageSendDTO): Promise<ApiResponse<Message>> => {
  return post('/conversation/message', data)
}

// 获取对话消息列表
export const getConversationMessages = (conversationId: number, params?: {
  pageNum?: number
  pageSize?: number
}): Promise<ApiResponse<PageResult<Message>>> => {
  return get(`/conversation/${conversationId}/messages`, params)
}
