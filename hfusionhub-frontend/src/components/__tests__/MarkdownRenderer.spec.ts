import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MarkdownRenderer from '../MarkdownRenderer.vue'

describe('MarkdownRenderer', () => {
  beforeEach(() => {
    vi.stubGlobal('isSecureContext', false)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders markdown headings and emphasis', () => {
    const wrapper = mount(MarkdownRenderer, {
      props: { content: '# 标题\n\n**加粗** 与 *斜体*' },
    })
    expect(wrapper.find('h1').text()).toBe('标题')
    expect(wrapper.find('strong').text()).toBe('加粗')
    expect(wrapper.find('em').exists()).toBe(true)
  })

  it('renders lists and links', () => {
    const wrapper = mount(MarkdownRenderer, {
      props: { content: '- 第一项\n- 第二项\n\n[链接](https://example.com)' },
    })
    expect(wrapper.findAll('li')).toHaveLength(2)
    const link = wrapper.find('a')
    expect(link.attributes('href')).toBe('https://example.com')
  })

  it('strips script tags (XSS)', () => {
    const wrapper = mount(MarkdownRenderer, {
      props: { content: '正常文本\n\n<script>window.alert(1)</script>' },
    })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('window.alert')
  })

  it('strips inline event handlers (XSS)', () => {
    const wrapper = mount(MarkdownRenderer, {
      props: { content: '[点击](https://example.com "title")\n\n<img src=x onerror="alert(1)">' },
    })
    expect(wrapper.find('[onerror]').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('onerror')
  })

  it('wraps code blocks with a copy button', () => {
    const wrapper = mount(MarkdownRenderer, {
      props: { content: '```js\nconst a = 1\n```' },
    })
    const btn = wrapper.find('.code-copy-btn')
    expect(btn.exists()).toBe(true)
    expect(wrapper.find('pre code').text()).toContain('const a = 1')
  })

  it('renders nothing for empty content', () => {
    const wrapper = mount(MarkdownRenderer, { props: { content: '' } })
    // innerHTML 为空串：根 div 自身不算内容
    expect(wrapper.find('.markdown-body').element.innerHTML).toBe('')
  })

  it('copies code to clipboard on button click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      configurable: true,
    })

    const wrapper = mount(MarkdownRenderer, {
      props: { content: '```\n要复制的代码\n```' },
      attachTo: document.body,
    })

    await wrapper.find('.code-copy-btn').trigger('click')
    await vi.waitFor(() => {
      expect(writeText).toHaveBeenCalledWith('要复制的代码\n')
    })

    wrapper.unmount()
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  })
})
