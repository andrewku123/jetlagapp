import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App'
import { CrashBoundary } from './components/CrashScreen'
import { PasswordGate } from './components/PasswordGate'
import { watchForNewBuild } from './lib/version'

watchForNewBuild()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CrashBoundary>
      <PasswordGate>
        <App />
      </PasswordGate>
    </CrashBoundary>
  </StrictMode>,
)
