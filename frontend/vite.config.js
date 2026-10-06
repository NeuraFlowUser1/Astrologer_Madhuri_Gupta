import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import {surfaceManifestPlugin} from '../appointment-system/tools/build/surfaces.mjs'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    surfaceManifestPlugin({bookingModules:['src/pages/Booking.jsx','src/pages/BookingReceipt.jsx','src/pages/BookingAccess.jsx','src/booking/browser.mjs']}),
  ],
  server: {
    port: 3000,
    host: true,
    // WSL-mounted files need polling so a refresh cannot retain stale modules.
    watch: { usePolling: Boolean(process.env.WSL_DISTRO_NAME) || process.env.SARSA_DEV_POLL === '1', interval: 500 },
    proxy: {
      '/company': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/studio': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err, req, res) => {
            if (err.code === 'ECONNREFUSED') {
              if (res.writeHead && !res.headersSent) {
                res.writeHead(503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Backend server is initializing...' }));
              }
              return;
            }
            console.error('[vite] proxy error:', err.message);
          });
        }
      }
    }
  }
})
