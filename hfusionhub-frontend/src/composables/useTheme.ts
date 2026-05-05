import { ref, watch } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'hfusionhub-theme'
const preference = ref<ThemePreference>((localStorage.getItem(STORAGE_KEY) as ThemePreference) || 'dark')
const isDarkMode = ref(preference.value === 'dark')
let initialized = false

const systemDark = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches

const resolveDark = (pref: ThemePreference) => (pref === 'system' ? systemDark() : pref === 'dark')

const applyTheme = (pref: ThemePreference) => {
  const dark = resolveDark(pref)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  isDarkMode.value = dark
}

let mediaQuery: MediaQueryList | null = null
let onSystemChange: ((e: MediaQueryListEvent) => void) | null = null

export const useTheme = () => {
  const initializeTheme = () => {
    if (initialized) return
    applyTheme(preference.value)
    initialized = true
  }

  const setTheme = (pref: ThemePreference) => {
    preference.value = pref
    localStorage.setItem(STORAGE_KEY, pref)
    applyTheme(pref)
    // 跟随系统时监听系统变化；非 system 时移除监听
    mediaQuery?.removeEventListener?.('change', onSystemChange!)
    onSystemChange = null
    if (pref === 'system' && typeof window !== 'undefined') {
      mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      onSystemChange = (e: MediaQueryListEvent) => {
        isDarkMode.value = e.matches
        applyTheme(preference.value)
      }
      mediaQuery.addEventListener('change', onSystemChange)
    }
  }

  const toggleTheme = () => setTheme(isDarkMode.value ? 'light' : 'dark')

  watch(preference, (value) => localStorage.setItem(STORAGE_KEY, value))

  return { preference, isDarkMode, initializeTheme, setTheme, toggleTheme }
}
