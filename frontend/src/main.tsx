import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initTelemetry, rootOptions } from './telemetry'

initTelemetry().finally(() => createRoot(document.getElementById('root')!, rootOptions).render(
  <StrictMode>
    <App />
  </StrictMode>,
))
