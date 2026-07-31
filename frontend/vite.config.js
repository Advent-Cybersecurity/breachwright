import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // The packaged frontend is always served from Breachwright's HTTP root.
  // An absolute base keeps deep links and page refreshes from requesting
  // assets beneath routes such as /engagements/:id/assets.
  base: '/',
  server: {
    proxy: {
      '/api': 'http://localhost:13370'
    }
  }
})
