import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorState from '../ErrorState.vue'

describe('ErrorState', () => {
  it('renders default title and message', () => {
    const wrapper = mount(ErrorState)
    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.text()).toContain('数据加载出错')
  })

  it('renders custom message', () => {
    const wrapper = mount(ErrorState, {
      props: { message: '网络连接失败' },
    })
    expect(wrapper.text()).toContain('网络连接失败')
  })

  it('renders retry button by default', () => {
    const wrapper = mount(ErrorState)
    expect(wrapper.text()).toContain('重新加载')
  })

  it('hides retry button when showRetry is false', () => {
    const wrapper = mount(ErrorState, {
      props: { showRetry: false },
    })
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('emits retry event on button click', async () => {
    const wrapper = mount(ErrorState)
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
  })

  it('supports custom retry label', () => {
    const wrapper = mount(ErrorState, {
      props: { retryLabel: '重试加载' },
    })
    expect(wrapper.text()).toContain('重试加载')
  })
})
