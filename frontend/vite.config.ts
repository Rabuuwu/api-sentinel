import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,process.cwd(),'');
  const upstream=env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
  const pages=mode==='pages';
  if(pages){
    const api=new URL(env.VITE_API_BASE_URL || 'invalid');
    if(api.protocol!=='https:' || api.username || api.password || api.search || api.hash || api.pathname.replace(/\/$/,'')!=='/api/v1')
      throw new Error('Pages requires VITE_API_BASE_URL=https://your-api-host/api/v1 (no secrets).');
  }
  return {
    base: pages ? (env.VITE_BASE_PATH || '/api-sentinel/') : '/',
    build: { outDir: pages ? 'dist-pages' : 'dist' },
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: { proxy: { '/api': upstream, '/health': upstream } },
    test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.test.{ts,tsx}'], globals: true },
  };
});
