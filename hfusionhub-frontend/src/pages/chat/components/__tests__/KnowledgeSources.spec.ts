import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgeSources from '../KnowledgeSources.vue'

const source = {
  document_id: 195,
  document_name: '云帆智能退款与售后政策',
  score: 0.92,
  outline_path: ['售后', '退货'],
  content: '7 天无理由退货……',
}

describe('KnowledgeSources', () => {
  it('renders count and titles', () => {
    const wrapper = mount(KnowledgeSources, {
      props: { sources: [source, { ...source, document_id: 198, document_name: '物流配送政策' }], knowledgeBaseId: 101 },
    })
    expect(wrapper.text()).toContain('知识来源')
    expect(wrapper.text()).toContain('(2条)')
    expect(wrapper.text()).toContain('云帆智能退款与售后政策')
  })

  it('renders router-link when knowledge base context exists', () => {
    const wrapper = mount(KnowledgeSources, {
      props: { sources: [source], knowledgeBaseId: 101 },
    })
    // 动态 :is 渲染为原生 router-link 自定义元素（无 router 插件的 jsdom）
    const link = wrapper.find('router-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('to')).toBe('/knowledge-base/101/chunks/195')
  })

  it('renders plain div without knowledge base context', () => {
    const wrapper = mount(KnowledgeSources, {
      props: { sources: [source], knowledgeBaseId: null },
    })
    expect(wrapper.find('router-link-stub').exists()).toBe(false)
    expect(wrapper.text()).toContain('7 天无理由退货……')
  })

  it('falls back to title then placeholder for missing names', () => {
    const wrapper = mount(KnowledgeSources, {
      props: {
        sources: [{ title: '标题回退' }, { score: 0.5 }],
        knowledgeBaseId: null,
      },
    })
    expect(wrapper.text()).toContain('标题回退')
    expect(wrapper.text()).toContain('文档 #未知')
  })

  it('renders score as percentage and hides empty score', () => {
    const wrapper = mount(KnowledgeSources, {
      props: { sources: [source, { title: '无分' }], knowledgeBaseId: null },
    })
    expect(wrapper.text()).toContain('92%')
  })

  it('renders outline path and content preview', () => {
    const wrapper = mount(KnowledgeSources, {
      props: { sources: [source], knowledgeBaseId: null },
    })
    expect(wrapper.text()).toContain('售后 > 退货')
  })
})
