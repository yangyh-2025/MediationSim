import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 59871,
    proxy: {
      '/api': 'http://localhost:59870',
    },
  },
});
