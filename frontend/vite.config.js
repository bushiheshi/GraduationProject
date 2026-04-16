import path from 'node:path';

import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

export default defineConfig({
  root: path.resolve(__dirname, 'teacher-src'),
  base: '/frontend/teacher/',
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:18080',
    },
  },
  build: {
    outDir: path.resolve(__dirname, 'teacher'),
    emptyOutDir: true,
  },
});
