import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Relative base so the build works from any folder (and as a published artifact).
export default defineConfig({
  base: './',
  plugins: [react()],
  // The single bundle carries the whole dataset (about 430 kB of JSON), so it is large on purpose.
  build: { chunkSizeWarningLimit: 1000 },
})
