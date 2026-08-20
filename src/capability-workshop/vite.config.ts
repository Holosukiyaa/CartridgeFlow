import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const authoringApiTarget = process.env.AUTHORING_API_TARGET || 'http://127.0.0.1:8765'

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/capabilities/' : '/',
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': authoringApiTarget,
    },
  },
}))
