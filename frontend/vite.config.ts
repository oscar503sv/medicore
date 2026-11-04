import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv, type PluginOption } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Inject a strict Content-Security-Policy meta tag into the PRODUCTION index.html.
 * Build-only: in dev, @vitejs/plugin-react injects an inline HMR preamble that a strict
 * `script-src 'self'` would block. `frame-ancestors` cannot be set via meta — the reverse
 * proxy should add it as a real header (see README → Deployment).
 */
function injectCsp(apiBaseUrl: string): PluginOption {
  // Split-origin deployments need the API origin in connect-src; same-origin needs none.
  let apiOrigin = ''
  try {
    apiOrigin = ` ${new URL(apiBaseUrl).origin}`
  } catch {
    // relative base URL (default "/api/v1") → 'self' already covers it
  }
  const policy = [
    "default-src 'self'",
    "script-src 'self'",
    // 'unsafe-inline' covers React style={} attributes; Google Fonts serves the stylesheet.
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    `connect-src 'self'${apiOrigin}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-src 'none'",
  ].join('; ')

  return {
    name: 'inject-csp',
    apply: 'build',
    transformIndexHtml(html) {
      return html.replace(
        '<meta charset="UTF-8" />',
        `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`,
      )
    },
  }
}

/**
 * Stamp each build with an id: compiled into the app (`__BUILD_ID__`) and published as
 * `/version.json`. A tab still running an older build notices the mismatch and offers a
 * reload (see UpdateNotice). nginx serves version.json uncached, like index.html.
 */
const BUILD_ID = Date.now().toString(36)

function versionFile(): PluginOption {
  return {
    name: 'version-file',
    apply: 'build',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source: JSON.stringify({ build: BUILD_ID }),
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Where `vite dev` proxies /api requests (only used in development).
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [react(), injectCsp(env.VITE_API_BASE_URL || '/api/v1'), versionFile()],
    define: { __BUILD_ID__: JSON.stringify(BUILD_ID) },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
