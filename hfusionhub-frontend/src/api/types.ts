// 通用响应类型
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

// 分页查询参数
export interface PageQuery {
  page: number
  pageSize: number
}

// 分页结果
export interface PageResult<T> {
  records: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
  hasPrevious: boolean
  hasNext: boolean
}

// 用户相关类型
export interface LoginForm {
  username: string
  password: string
}

export interface RegisterForm {
  username: string
  password: string
  nickname?: string
  email?: string
  phone?: string
}

export interface UserInfo {
  id: number
  username: string
  nickname: string
  email: string
  phone: string
  avatar: string
  status: number
  createdAt: string
}

// 知识库相关类型
export interface KnowledgeBase {
  id: number
  name: string
  description: string
  userId: number
  username?: string
  status: number
  documentCount?: number
  createdAt: string
  updatedAt: string
}

export interface KnowledgeBaseCreateDTO {
  name: string
  description?: string
}

export interface KnowledgeBaseUpdateDTO {
  name?: string
  description?: string
  status?: number
}

// 文档相关类型
export interface Document {
  id: number
  knowledgeBaseId: number
  knowledgeBaseName: string
  title: string
  fileType: string
  fileSize: number
  chunkCount: number
  status: number
  statusDesc: string
  errorMessage: string | null
  username?: string
  createdAt: string
  updatedAt: string
  recycledAt?: string | null
  recycleExpiresAt?: string | null
}

export interface DocumentUploadDTO {
  file: File
  kbId: number
}

// 对话相关类型
export interface Conversation {
  id: number
  title: string
  knowledgeBaseId: number
  knowledgeBaseName?: string
  promptTemplateId?: number
  promptTemplateName?: string
  userId: number
  userName?: string
  messageCount?: number
  lastMessage?: string
  createdAt: string
  updatedAt: string
}

export interface Message {
  id: number
  conversationId: number
  role: 'user' | 'assistant'
  content: string
  tokenCount?: number
  model?: string
  sources?: Array<{
    document_id?: string | number
    chunk_id?: string
    knowledge_base_id?: number
    title?: string
    document_name?: string
    outline_path?: string[]
    content: string
    excerpt?: string
    score: number
    source?: string
  }>
  createdAt: string
}

export interface ConversationCreateDTO {
  title: string
  knowledgeBaseId?: number
  promptTemplateId?: number
}

export interface MessageSendDTO {
  conversationId: number
  content: string
  requestId?: string
}
