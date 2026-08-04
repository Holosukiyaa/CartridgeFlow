import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const creatorApiTarget = process.env.CREATOR_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/creator/' : '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': creatorApiTarget,
    },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' },
}))
