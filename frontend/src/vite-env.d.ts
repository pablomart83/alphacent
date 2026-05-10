/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_WS_BASE_URL: string
  readonly VITE_BUILD_SHA?: string
  readonly VITE_BUILD_TIMESTAMP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '@fontsource-variable/inter'
declare module '@fontsource-variable/jetbrains-mono'
