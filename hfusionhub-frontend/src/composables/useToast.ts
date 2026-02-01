import { ref } from 'vue'

export interface Toast {
  id: number
  message: string
  type: 'success' | 'error' | 'warning' | 'info'
}

const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  const addToast = (message: string, type: Toast['type'] = 'info', duration = 3000) => {
    const id = nextId++
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, duration)
  }

  const success = (message: string) => addToast(message, 'success')
  const error = (message: string) => addToast(message, 'error', 5000)
  const warning = (message: string) => addToast(message, 'warning', 4000)
  const info = (message: string) => addToast(message, 'info')

  return { toasts, success, error, warning, info }
}
