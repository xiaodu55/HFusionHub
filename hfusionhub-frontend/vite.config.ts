import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
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
})
