import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../../i18n'
import { zhCN } from '../../locales/zh-CN'
import { enUS } from '../../locales/en-US'
import { getInitialLocale, useLocale } from '../useLocale'

const keyPaths = (obj: unknown, prefix = ''): string[] =>
  obj && typeof obj === 'object'
    ? Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
        v && typeof v === 'object' ? keyPaths(v, `${prefix}${k}.`) : [`${prefix}${k}`],
      )
    : []

describe('i18n skeleton', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('zh-CN and en-US share the exact same key structure', () => {
    expect(keyPaths(enUS).sort()).toEqual(keyPaths(zhCN).sort())
  })

  it('resolves nav and chat keys in both locales', () => {
    i18n.global.locale.value = 'zh-CN'
    expect(i18n.global.t('nav.groups.use')).toBe('使用')
    expect(i18n.global.t('nav.items./chat.label')).toBe('智能对话')
    i18n.global.locale.value = 'en-US'
    expect(i18n.global.t('nav.groups.use')).toBe('Use')
    expect(i18n.global.t('nav.items./chat.label')).toBe('Chat')
    expect(i18n.global.t('chat.inputPlaceholder')).toContain('Enter to send')
  })

  it('falls back to zh-CN for missing en keys', () => {
    i18n.global.locale.value = 'en-US'
    // 键结构一致时不会触发回退；此处验证 fallbackLocale 指向 zh-CN
    expect(i18n.global.fallbackLocale.value).toBe('zh-CN')
  })

  it('useLocale persists preference and toggles', () => {
    expect(getInitialLocale()).toBe('zh-CN')
    const { toggleLocale, locale } = useLocale()
    toggleLocale()
    expect(locale.value).toBe('en-US')
    expect(localStorage.getItem('hfusionhub-locale')).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
    toggleLocale()
    expect(locale.value).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })
})
