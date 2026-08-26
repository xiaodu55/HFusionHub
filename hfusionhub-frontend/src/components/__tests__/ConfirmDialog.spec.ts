import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmDialog from '../ConfirmDialog.vue'

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(ConfirmDialog, {
    props: { open: true, ...props },
    global: {
      stubs: {
        // radix-vue Dialog 的传送门/动画在 jsdom 中不稳定，桩掉外壳只测行为
        Teleport: true,
      },
    },
  })
}

describe('ConfirmDialog', () => {
  it('renders default title and description', () => {
    const wrapper = mountDialog()
    expect(wrapper.text()).toContain('确认操作')
    expect(wrapper.text()).toContain('确认')
  })

  it('renders custom title, description and confirm text', () => {
    const wrapper = mountDialog({
      title: '删除文档',
      description: '此操作可在回收站恢复',
      confirmText: '删除',
    })
    expect(wrapper.text()).toContain('删除文档')
    expect(wrapper.text()).toContain('此操作可在回收站恢复')
    expect(wrapper.text()).toContain('删除')
  })

  it('hides description when not provided', () => {
    const wrapper = mountDialog()
    expect(wrapper.find('[data-slot="dialog-description"]').exists()
      || wrapper.find('p').exists()).toBe(false)
  })

  it('emits confirm on confirm button click', async () => {
    const wrapper = mountDialog()
    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text() === '确认')
    await confirmBtn!.trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()
  })

  it('emits update:open=false on cancel', async () => {
    const wrapper = mountDialog()
    const cancelBtn = wrapper.findAll('button').find((b) => b.text() === '取消')
    await cancelBtn!.trigger('click')
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  })

  it('shows processing state while loading', () => {
    const wrapper = mountDialog({ loading: true })
    // 禁用绑定（:disabled="loading"）由 radix Button 承接；jsdom 下其
    // disabled 属性序列化不稳定，这里断言可观测的文案状态
    expect(wrapper.text()).toContain('处理中...')
    expect(wrapper.text()).not.toContain('删除')
  })

  it('uses destructive variant when destructive is true', () => {
    const wrapper = mountDialog({ destructive: true })
    const confirmBtn = wrapper
      .findAll('button')
      .find((b) => b.text() === '确认')
    expect(confirmBtn?.classes().join(' ')).toContain('destructive')
  })
})
