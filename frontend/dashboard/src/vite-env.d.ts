/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Python financial API (backend/main.py). */
  readonly VITE_FINANCIAL_API_URL: string;
  /** Base URL of the Python ML scoring service (ml_service/main.py). */
  readonly VITE_ML_API_URL: string;
  /** User whose savings the dashboard renders, until auth exists. */
  readonly VITE_DASHBOARD_USER_ID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
