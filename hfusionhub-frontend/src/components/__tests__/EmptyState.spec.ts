import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '../EmptyState.vue'
import { BookOpen } from 'lucide-vue-next'

describe('EmptyState', () => {
  it('renders default title', () => {
    const wrapper = mount(EmptyState)
    expect(wrapper.text()).toContain('暂无数据')
  })

  it('renders custom title and description', () => {
    const wrapper = mount(EmptyState, {
      props: {
        title: '没有知识库',
        description: '创建您的第一个知识库',
      },
    })
    expect(wrapper.text()).toContain('没有知识库')
    expect(wrapper.text()).toContain('创建您的第一个知识库')
  })

  it('renders action button when showAction is true', () => {
    const wrapper = mount(EmptyState, {
      props: {
        showAction: true,
        action: '创建',
      },
    })
    expect(wrapper.text()).toContain('创建')
  })

  it('does not render action button by default', () => {
    const wrapper = mount(EmptyState)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('emits action event when button is clicked', async () => {
    const wrapper = mount(EmptyState, {
      props: { showAction: true },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('action')).toBeTruthy()
  })

  it('renders icon when provided', () => {
    const wrapper = mount(EmptyState, {
      props: { icon: BookOpen },
    })
    expect(wrapper.findComponent(BookOpen).exists()).toBe(true)
  })
})
