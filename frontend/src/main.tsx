import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppShell } from './app/AppShell'
import { AuthProvider } from './app/providers/AuthProvider'
import { LanguageProvider } from './app/providers/LanguageProvider'
import { ThemeProvider } from './app/providers/ThemeProvider'
import { AppRoutes } from './app/router'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <LanguageProvider>
        <ThemeProvider>
          <Toaster position="top-right" />
          <AuthProvider>
            <AppShell>
              <AppRoutes />
            </AppShell>
          </AuthProvider>
        </ThemeProvider>
      </LanguageProvider>
    </BrowserRouter>
  </React.StrictMode>
)
