/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'

// The core serves /api, /media and /mcp. In development we proxy to a running
// core (default: the demo library on 8770). Host stays loopback so the core's
// solo-mode rules (loopback client + loopback Host header) still apply.
const core = process.env.MC_CORE ?? 'http://127.0.0.1:8770'

// Lightning CSS browser targets: light-dark() needs Chromium 123 / Firefox 120 / Safari 17.5.
const v = (major: number, minor = 0) => (major << 16) | (minor << 8)

export default defineConfig({
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
  css: {
    transformer: 'lightningcss',
    lightningcss: { targets: { chrome: v(123), firefox: v(120), safari: v(17, 5) } },
    modules: {},
  },
  build: {
    cssMinify: 'lightningcss',
    target: ['chrome123', 'firefox120', 'safari17.5'],
    sourcemap: true,
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': { target: core, changeOrigin: false },
      '/media': { target: core, changeOrigin: false },
      '/mcp': { target: core, changeOrigin: false },
    },
  },
  preview: {
    proxy: {
      '/api': { target: core, changeOrigin: false },
      '/media': { target: core, changeOrigin: false },
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})
