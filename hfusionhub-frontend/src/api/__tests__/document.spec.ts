import { beforeEach, describe, expect, it, vi } from 'vitest'
import { del, get, post, put } from '../request'
import {
  deleteDocument,
  getDocumentsByKbId,
  getRecycleBin,
  parseDocument,
  purgeDocument,
  restoreDocument,
  updateDocument,
  uploadDocument,
} from '../document'

vi.mock('../request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}))

describe('document API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uploads a file with knowledge base and custom title fields', () => {
    const file = new File(['content'], 'guide.md', { type: 'text/markdown' })

    uploadDocument(file, 7, 'Custom title')

    expect(post).toHaveBeenCalledOnce()
    const [url, body, config] = vi.mocked(post).mock.calls[0]
    expect(url).toBe('/document/upload')
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('file')).toBe(file)
    expect((body as FormData).get('knowledgeBaseId')).toBe('7')
    expect((body as FormData).get('title')).toBe('Custom title')
    expect(config).toEqual({
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  })

  it('uses the filename when upload title is omitted', () => {
    const file = new File(['content'], 'guide.md', { type: 'text/markdown' })

    uploadDocument(file, 7)

    const body = vi.mocked(post).mock.calls[0][1] as FormData
    expect(body.get('title')).toBe('guide.md')
  })

  it('forwards document updates and deletion to resource routes', () => {
    updateDocument(9, { title: 'Renamed', content: 'Updated' })
    deleteDocument(9)

    expect(put).toHaveBeenCalledWith('/document/9', {
      title: 'Renamed',
      content: 'Updated',
    })
    expect(del).toHaveBeenCalledWith('/document/9')
  })

  it('forwards recycle-bin list filters', () => {
    const params = { page: 2, pageSize: 15, title: 'report' }

    getRecycleBin(params)

    expect(get).toHaveBeenCalledWith('/document/recycle-bin', params)
  })

  it('uses distinct restore, purge, parse, and knowledge-base routes', () => {
    restoreDocument(9)
    purgeDocument(9)
    parseDocument(9, 'ollama')
    getDocumentsByKbId(7, { page: 1, pageSize: 20 })

    expect(post).toHaveBeenCalledWith('/document/9/restore')
    expect(del).toHaveBeenCalledWith('/document/9/purge')
    expect(post).toHaveBeenCalledWith('/document/9/parse', { model: 'ollama' })
    expect(get).toHaveBeenCalledWith('/document/list/7', {
      page: 1,
      pageSize: 20,
    })
  })
})
