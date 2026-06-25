import { ref, watch, onUnmounted, type Ref } from 'vue'
import { get } from '@/api/request'

/**
 * 把需要鉴权的头像 URL 转为本地 blob URL。
 *
 * `<img>` 标签无法携带 satoken 请求头，直接引用后端头像地址会 401/403，
 * 因此用 axios（自动注入 satoken）以 blob 拉取，再转 objectURL 展示。
 * 输入 URL 变化（如上传成功后加时间戳破缓存）时自动重新拉取；
 * 组件卸载时释放 objectURL。
 */
export function useAvatarImage(avatarUrl: Ref<string | undefined | null>) {
  const blobUrl = ref('')

  watch(
    avatarUrl,
    async (rawUrl) => {
      if (!rawUrl) {
        blobUrl.value = ''
        return
      }
      // 后端返回的地址可能带 /api 前缀，axios baseURL 也是 /api，
      // 直接拼会变成 /api/api/... 404 —— 剥离重复前缀
      const base = '/api'
      const url = rawUrl.startsWith(`${base}/`) ? rawUrl.slice(base.length) : rawUrl
      try {
        const data = (await get(url, undefined, { responseType: 'blob' })) as unknown as Blob
        if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
        blobUrl.value = data instanceof Blob ? URL.createObjectURL(data) : ''
      } catch {
        blobUrl.value = ''
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
  })

  return blobUrl
}
