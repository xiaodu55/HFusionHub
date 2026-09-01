import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageItem from '../MessageItem.vue'
import type { Message } from '@/api/types'

const baseMessage = (over: Partial<Message> = {}): Message => ({
  id: 100,
  conversationId: 1,
  role: 'assistant',
  content: '回答内容',
  createdAt: '2026-09-09 12:00:00',
  ...over,
} as Message)

const mountItem = (message: Message, props: Record<string, unknown> = {}) =>
  mount(MessageItem, {
    props: {
      message,
      streaming: false,
      sessionStreaming: false,
      ttsEnabled: false,
      speaking: false,
      knowledgeBaseId: 101,
      ...props,
    },
    global: {
      stubs: {
        MarkdownRenderer: { template: '<div class="md-stub">{{ content }}</div>', props: ['content'] },
      },
    },
  })

describe('MessageItem', () => {
  it('renders assistant content through markdown stub', () => {
    const wrapper = mountItem(baseMessage())
    expect(wrapper.find('.md-stub').text()).toBe('回答内容')
  })

  it('renders user messages with avatar alignment and plain text', () => {
    const wrapper = mountItem(baseMessage({ role: 'user', content: '用户提问' }))
    expect(wrapper.text()).toContain('用户提问')
    expect(wrapper.find('.md-stub').exists()).toBe(false)
  })

  it('shows thinking placeholder for empty streaming message', () => {
    const wrapper = mountItem(baseMessage({ content: '' }), { streaming: true })
    expect(wrapper.text()).toContain('思考中...')
  })

  it('shows generating indicator for non-empty streaming message', () => {
    const wrapper = mountItem(baseMessage(), { streaming: true })
    expect(wrapper.text()).toContain('生成中...')
  })

  it('emits copy with the message payload', async () => {
    const msg = baseMessage()
    const wrapper = mountItem(msg)
    await wrapper.findAll('button').find((b) => b.attributes('title') === '复制内容')!.trigger('click')
    expect(wrapper.emitted('copy')?.[0]).toEqual([msg])
  })

  it('hides regenerate/feedback buttons while session is streaming', () => {
    const wrapper = mountItem(baseMessage(), { sessionStreaming: true })
    expect(wrapper.find('[title="重新生成回答"]').exists()).toBe(false)
    expect(wrapper.find('[title="回答有帮助"]').exists()).toBe(false)
  })

  it('shows regenerate button for healthy assistant answers', () => {
    const wrapper = mountItem(baseMessage())
    expect(wrapper.find('[title="重新生成回答"]').exists()).toBe(true)
  })

  it('detects error messages and offers retry instead of regenerate', () => {
    const wrapper = mountItem(baseMessage({ model: 'error', content: '⚠️ 失败' }))
    expect(wrapper.find('[title="重新生成回答"]').exists()).toBe(false)
    const retry = wrapper.findAll('button').find((b) => b.text().includes('重试'))
    expect(retry).toBeTruthy()
  })

  it('emits retry for error messages', async () => {
    const msg = baseMessage({ model: 'error', content: '⚠️ 失败' })
    const wrapper = mountItem(msg)
    await wrapper.findAll('button').find((b) => b.text().includes('重试'))!.trigger('click')
    expect(wrapper.emitted('retry')?.[0]).toEqual([msg])
  })

  it('renders knowledge sources for assistant messages', () => {
    const wrapper = mountItem(baseMessage({
      sources: [{ document_id: 195, document_name: '退款政策', score: 0.9, content: '来源内容' }],
    }))
    expect(wrapper.text()).toContain('知识来源')
    expect(wrapper.text()).toContain('退款政策')
  })

  it('highlights active feedback state', () => {
    const wrapper = mountItem(baseMessage(), { feedback: 'UP' })
    const up = wrapper.find('[title="回答有帮助"]')
    expect(up.classes().join(' ')).toContain('text-emerald-400')
  })
})
