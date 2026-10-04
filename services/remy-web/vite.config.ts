import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api/* to remy-api. The prefix is stripped so the API
// sees root-relative paths (mirrors nginx.conf in production). PORT and
// API_TARGET override the defaults (e.g. a second dev server against a
// sandbox API).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [react()],
    server: {
      port: Number(env.PORT || 3000),
      proxy: {
        '/api': {
          target: env.API_TARGET || 'http://localhost:8080',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
