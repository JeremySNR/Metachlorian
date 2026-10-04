import '@fontsource-variable/instrument-sans/wdth.css'
import '@fontsource-variable/jetbrains-mono'
import './styles/tokens.css'
import './styles/global.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { queryClient } from './api/queries'
import { router } from './routes/router'
import { applyPrefsToDocument, usePrefs } from './lib/store'

applyPrefsToDocument(usePrefs.getState())
usePrefs.subscribe((p) => applyPrefsToDocument(p))

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
