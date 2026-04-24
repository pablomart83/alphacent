import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Charts
          if (id.includes('node_modules/lightweight-charts')) {
            return 'charts-vendor';
          }
          // PDF generation (only loaded on demand)
          if (id.includes('node_modules/html2canvas') || id.includes('node_modules/jspdf')) {
            return 'pdf-vendor';
          }
          // React core
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router')) {
            return 'react-vendor';
          }
          // UI components (Radix)
          if (id.includes('node_modules/@radix-ui')) {
            return 'ui-vendor';
          }
          // Tables
          if (id.includes('node_modules/@tanstack/react-table')) {
            return 'table-vendor';
          }
          // Animations
          if (id.includes('node_modules/framer-motion')) {
            return 'animation-vendor';
          }
          // State management
          if (id.includes('node_modules/zustand')) {
            return 'state-vendor';
          }
          // Utilities
          if (id.includes('node_modules/date-fns') || id.includes('node_modules/clsx') || id.includes('node_modules/tailwind-merge')) {
            return 'util-vendor';
          }
          // Icons
          if (id.includes('node_modules/lucide-react')) {
            return 'icon-vendor';
          }
        },
      },
    },
    chunkSizeWarningLimit: 1000,
    minify: 'esbuild',
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
