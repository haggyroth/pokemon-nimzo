import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Suppress expected proxy noise in the Vite dev-server terminal.
//   ECONNREFUSED — backend not up yet
//   ECONNRESET   — client closed the tab / navigated away mid-stream
//   EPIPE        — write to a dead socket after browser disconnect
// Unexpected errors (timeouts, TLS failures, etc.) still surface.
const SILENT_CODES = new Set(['ECONNREFUSED', 'ECONNRESET', 'EPIPE'])
function silenceRefused(proxy) {
  proxy.on('error', (err) => {
    if (!SILENT_CODES.has(err.code)) console.error('[proxy]', err.message)
  })
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:5001', configure: silenceRefused },
      '/ws':  { target: 'ws://localhost:5001', ws: true, configure: silenceRefused },
    },
  },
})
