import { ref } from 'vue'

/** 支持的语言（骨架期：zh-CN 全量默认，en-US 导航/聊天骨架）。 */
export type Locale = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'hfusionhub-locale'

export const SUPPORTED_LOCALES: Locale[] = ['zh-CN', 'en-US']

export const getInitialLocale = (): Locale =>
  localStorage.getItem(STORAGE_KEY) === 'en-US' ? 'en-US' : 'zh-CN'

/** 当前语言偏好（模块级共享，i18n.ts 经 watchEffect 与实例双向同步）。 */
export const locale = ref<Locale>(getInitialLocale())

/** 语言偏好（镜像 useTheme 的持久化模式），与 vue-i18n 实例双向同步。 */
export const useLocale = () => {
  const setLocale = (next: Locale) => {
    locale.value = next
    localStorage.setItem(STORAGE_KEY, next)
    document.documentElement.lang = next
  }
  const toggleLocale = () => setLocale(locale.value === 'zh-CN' ? 'en-US' : 'zh-CN')
  return { locale, setLocale, toggleLocale }
}
