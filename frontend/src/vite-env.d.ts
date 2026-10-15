/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OPS_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
