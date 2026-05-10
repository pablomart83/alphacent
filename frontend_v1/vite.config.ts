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
  optimizeDeps: {
    // Pre-bundle lucide-react into a single ESM chunk during dep optimization.
    // Without this, Vite transforms all 3800+ individual icon files at build time → 17s.
    // With this, it's pre-processed once into a single optimized module → ~5s.
    include: ['lucide-react'],
    force: false,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/lightweight-charts')) return 'charts-vendor';
          if (id.includes('node_modules/html2canvas') || id.includes('node_modules/jspdf')) return 'pdf-vendor';
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router')) return 'react-vendor';
          if (id.includes('node_modules/@radix-ui')) return 'ui-vendor';
          if (id.includes('node_modules/@tanstack/react-table')) return 'table-vendor';
          if (id.includes('node_modules/framer-motion')) return 'animation-vendor';
          if (id.includes('node_modules/zustand')) return 'state-vendor';
          if (id.includes('node_modules/date-fns') || id.includes('node_modules/clsx') || id.includes('node_modules/tailwind-merge')) return 'util-vendor';
          if (id.includes('node_modules/lucide-react')) return 'icon-vendor';
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
