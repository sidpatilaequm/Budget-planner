import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, API calls to /api are forwarded to the FastAPI server.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true } },
  },
})
