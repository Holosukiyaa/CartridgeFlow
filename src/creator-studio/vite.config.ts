import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/creator/' : '/',
  plugins: [react()],
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' },
}))
