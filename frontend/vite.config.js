import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxying /api in dev means the browser sees one origin, so CORS only has
    // to be configured for the production deployment.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
