import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    global: 'globalThis',
  },
  build: {
    // Plotly is large even as a custom bundle; split it so the app shell and the
    // data-loading path are not blocked behind it.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('plotly.js')) return 'plotly'
          if (id.includes('d3-force') || id.includes('d3-')) return 'd3'
          if (id.includes('node_modules/react')) return 'react'
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
})
