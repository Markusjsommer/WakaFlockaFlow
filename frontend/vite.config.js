import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server proxies all /api calls to the FastAPI backend on :8001.
// (:8000 is a separate pre-existing CytoFlow app — do not target it.)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8001',
    },
  },
});
