import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8765'

// Vite 配置：dev server 代理 /api 到后端，构建产物输出到 ../web_static
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 所有 /api 请求代理到后端服务
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/packages': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/artifacts': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    // 构建产物覆盖旧的静态文件目录
    outDir: '../web_static',
    emptyOutDir: true,
  },
})
