import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const API_URL = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/best-ball': API_URL,
      '/healthz': API_URL,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
