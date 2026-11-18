import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv, searchForWorkspaceRoot } from 'vite';

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, '.', '');
	const apiTarget = env.DICTARE_API_TARGET || 'http://127.0.0.1:8770';

	return {
		plugins: [sveltekit()],
		server: {
			// Optional shared dependency directory for isolated Git worktrees.
			// Keep Vite's strict boundary and do not expose the whole parent folder.
			fs: { allow: [
				searchForWorkspaceRoot('.'),
				'../README.md', // Vite runs from ui/, like loadEnv above.
				...(env.DICTARE_DEV_DEPENDENCIES ? [env.DICTARE_DEV_DEPENDENCIES] : [])
			] },
			proxy: {
				'/api': { target: apiTarget, changeOrigin: false },
				'/openvip': apiTarget
			}
		}
	};
});
