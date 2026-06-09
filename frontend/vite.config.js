import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Suppress ECONNREFUSED noise in the Vite dev-server terminal when the
// Python backend hasn't started yet.  Real proxy errors (non-refusal) still
// surface so genuine failures aren't hidden.
function silenceRefused(proxy) {
  proxy.on('error', (err) => {
    if (err.code !== 'ECONNREFUSED') console.error('[proxy]', err.message)
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
