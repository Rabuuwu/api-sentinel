import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,process.cwd(),'');
  const upstream=env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
  return {
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: { proxy: { '/api': upstream, '/health': upstream } },
    test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.test.{ts,tsx}'], globals: true },
  };
});
