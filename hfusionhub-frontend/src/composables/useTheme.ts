import { ref } from 'vue'

const STORAGE_KEY = 'hfusionhub-theme'
const isDarkMode = ref(true)
let initialized = false

const applyTheme = (dark: boolean) => {
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

export const useTheme = () => {
  const initializeTheme = () => {
    if (initialized) return
    const storedTheme = localStorage.getItem(STORAGE_KEY)
    isDarkMode.value = storedTheme ? storedTheme === 'dark' : true
    applyTheme(isDarkMode.value)
    initialized = true
  }

  const setTheme = (dark: boolean) => {
    isDarkMode.value = dark
    applyTheme(dark)
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  }

  const toggleTheme = () => setTheme(!isDarkMode.value)

  return { isDarkMode, initializeTheme, setTheme, toggleTheme }
}
