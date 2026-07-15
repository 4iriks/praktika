/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_MOCK_FORCE_ERROR?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
