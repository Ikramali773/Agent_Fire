import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './design-system/tokens.css'
import './design-system/base.css'
import { AuthProvider } from './auth/AuthContext'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
