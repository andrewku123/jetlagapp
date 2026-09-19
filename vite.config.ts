import { execSync } from 'node:child_process'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Stamp every build so a running page can tell it is older than what the server
// now serves (see src/lib/version.ts). The same id is compiled into the bundle
// and written to version.json next to it.
function buildId(): string {
  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim()
  } catch {
    return String(Date.now())
  }
}

function emitVersion(id: string): Plugin {
  return {
    name: 'emit-version-json',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ build: id }) })
    },
  }
}

const BUILD_ID = buildId()

// base is set for GitHub Pages project-page hosting; override with BASE env if needed.
export default defineConfig({
  plugins: [react(), emitVersion(BUILD_ID)],
  base: process.env.BASE ?? '/',
  define: { __BUILD_ID__: JSON.stringify(BUILD_ID) },
})
