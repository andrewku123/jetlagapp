import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base is set for GitHub Pages project-page hosting; override with BASE env if needed.
export default defineConfig({
  plugins: [react()],
  base: process.env.BASE ?? '/',
})
