import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatApprovalCard, { type ChatApprovalPrompt } from '../ChatApprovalCard.vue'

const mountCard = (prompt: ChatApprovalPrompt = { toolName: 'write_note' }, busy = false) =>
  mount(ChatApprovalCard, { props: { prompt, busy } })

describe('ChatApprovalCard', () => {
  it('renders write_note summary for write_note tool', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('把内容整理成笔记保存到知识库')
  })

  it('renders generic tool summary for other tools', () => {
    const wrapper = mountCard({ toolName: 'search_tool' })
    expect(wrapper.text()).toContain('调用工具 search_tool')
  })

  it('renders unknown-tool fallback when toolName missing', () => {
    const wrapper = mountCard({ toolName: undefined as unknown as string })
    expect(wrapper.text()).toContain('调用工具 未知工具')
  })

  it('renders arguments summary when provided', () => {
    const wrapper = mountCard({ toolName: 'write_note', argumentsSummary: '退款政策笔记' })
    expect(wrapper.text()).toContain('退款政策笔记')
  })

  it('emits decide=approved on confirm click', async () => {
    const wrapper = mountCard()
    const buttons = wrapper.findAll('button')
    await buttons.find((b) => b.text().includes('同意执行'))!.trigger('click')
    expect(wrapper.emitted('decide')?.[0]).toEqual(['approved'])
  })

  it('emits decide=denied on reject click', async () => {
    const wrapper = mountCard()
    const buttons = wrapper.findAll('button')
    await buttons.find((b) => b.text().includes('拒绝'))!.trigger('click')
    expect(wrapper.emitted('decide')?.[0]).toEqual(['denied'])
  })

  it('disables buttons while busy', () => {
    const wrapper = mountCard({ toolName: 'write_note' }, true)
    expect(wrapper.findAll('button').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  })
})
