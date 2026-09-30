import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// In development the UI calls /api/* and Vite forwards it to the local Python server (backend/local_server.py).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_DEV_API || 'http://localhost:8000', changeOrigin: true, timeout: 120000 },
    },
  },
});
