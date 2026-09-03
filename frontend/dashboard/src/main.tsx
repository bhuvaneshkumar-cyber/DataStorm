import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './auth/AuthContext';
import { I18nProvider } from './i18n';
import './index.css';

// I18nProvider wraps AuthProvider rather than the other way round: signing in
// switches the UI to the account's stored language, so the auth layer needs the
// language setter, and the sign-in screen needs translation before any account
// exists to read one from.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  </StrictMode>,
);
