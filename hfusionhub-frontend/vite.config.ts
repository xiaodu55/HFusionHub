import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// 手动分包：把稳定的大依赖归并为 vendor chunk，避免 ~200 个小 chunk
const manualChunks = (id: string) => {
  if (!id.includes('node_modules')) return undefined
  if (id.includes('node_modules/vue') || id.includes('node_modules/@vue')) return 'vendor-vue'
  if (id.includes('node_modules/pinia')) return 'vendor-vue'
  if (id.includes('node_modules/vue-router')) return 'vendor-vue'
  if (id.includes('node_modules/axios')) return 'vendor-http'
  if (id.includes('node_modules/marked')) return 'vendor-markdown'
  if (id.includes('node_modules/dompurify')) return 'vendor-markdown'
  if (id.includes('node_modules/radix-vue')) return 'vendor-ui'
  if (id.includes('node_modules/lucide-vue-next')) return 'vendor-icons'
  if (id.includes('node_modules/tailwind-merge') || id.includes('node_modules/class-variance-authority') || id.includes('node_modules/clsx')) return 'vendor-ui'
  // 其余 node_modules 依赖统一归并，避免碎片化
  return 'vendor-misc'
}

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    // 允许局域网/内网穿透（cpolar 等）通过外部域名访问：
    // host: true 监听所有网卡；allowedHosts: true 放开 Host 校验。
    // 生产环境走 Nginx，不受此影响。
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  // 生产预览（vite preview）：公网穿透用打包产物（无 transform，加载快）
  preview: {
    port: 3000,
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
