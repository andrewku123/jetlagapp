import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import '../index.css'
import { CrashBoundary } from '../components/CrashScreen'
import { PasswordGate } from '../components/PasswordGate'
import ReviewApp from './ReviewApp'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CrashBoundary>
      <PasswordGate>
        <ReviewApp />
      </PasswordGate>
    </CrashBoundary>
  </StrictMode>,
)
