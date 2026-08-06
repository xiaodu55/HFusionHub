import { createI18n } from 'vue-i18n'
import { watchEffect } from 'vue'
import { zhCN } from './locales/zh-CN'
import { enUS } from './locales/en-US'
import { getInitialLocale, locale } from './composables/useLocale'

const i18n = createI18n({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

// useLocale 的偏好与 i18n 实例双向同步；同时驱动 <html lang>
watchEffect(() => {
  i18n.global.locale.value = locale.value
  document.documentElement.lang = locale.value
})

export default i18n
