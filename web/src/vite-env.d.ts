/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_ANON_KEY: string;
  /** Dirección pública del sitio de Mechanified. Opcional: sin ella, el origen actual. */
  readonly VITE_URL_SITIO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
