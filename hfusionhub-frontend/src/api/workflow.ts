import { get, post, put, del } from './request'

export interface WorkflowDef {
  id?: number
  name: string
  description?: string
  nodes: any[]
  edges: any[]
  status?: string
  createdAt?: string
  updatedAt?: string
}

export const listWorkflows = (page = 1, pageSize = 20) =>
  get<{ data: { records: WorkflowDef[]; total: number } }>('/workflow/list', { page, pageSize })

export const getWorkflow = (id: number) =>
  get<{ data: WorkflowDef }>(`/workflow/${id}`)

export const createWorkflow = (data: WorkflowDef) =>
  post<{ data: WorkflowDef }>('/workflow', data)

export const updateWorkflow = (id: number, data: Partial<WorkflowDef>) =>
  put<{ data: WorkflowDef }>(`/workflow/${id}`, data)

export const deleteWorkflow = (id: number) =>
  del(`/workflow/${id}`)
