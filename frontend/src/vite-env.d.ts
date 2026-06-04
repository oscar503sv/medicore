/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend base URL for the built app (e.g. https://api.example.com/api/v1).
   *  Leave unset to use the same-origin relative path "/api/v1". */
  readonly VITE_API_BASE_URL?: string
  /** Dev-only: where `vite dev` proxies /api requests (default http://localhost:8000). */
  readonly VITE_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
