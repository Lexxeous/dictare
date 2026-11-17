import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const apiTarget = env.DICTARE_API_TARGET || 'http://127.0.0.1:8770';

  return {
    plugins: [sveltekit()],
    server: {
      proxy: {
        '/api': apiTarget,
        '/openvip': apiTarget
      }
    }
  };
});
