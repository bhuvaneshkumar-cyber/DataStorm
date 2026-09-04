/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Python financial API (backend/main.py). Defaults to localhost:8000. */
  readonly VITE_BACKEND_URL?: string;
  /** Base URL of the Python ML scoring service (ml_service/main.py). Defaults to localhost:8001. */
  readonly VITE_ML_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
