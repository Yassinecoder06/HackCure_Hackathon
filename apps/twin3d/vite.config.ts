import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Dev: the browser talks to this server, which forwards /api (REST and the WebSocket stream) to the ward
// server. The same relative URLs work behind Caddy in the demo, so TLS is the proxy's job, not ours.
export default defineConfig(({ mode }) => {
  // TWIN_API_TARGET (in apps/twin3d/.env.local, which git ignores) points the dev proxy at another ward server,
  // e.g. when port 8000 is reserved by Windows.
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.TWIN_API_TARGET || 'http://localhost:8000';
  return {
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': { target, changeOrigin: true, ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 1700 },
  };
});
