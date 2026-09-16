import { Component, type ErrorInfo, type ReactNode } from 'react'
import { clearSave, readRawSave } from '../lib/storage'

// A crash used to leave a black page with no way out on a phone: no console, and
// the saved board that triggered it reloads every time. This shows what broke and
// lets the board be copied out before it is wiped.
export class CrashBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('app crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return <CrashScreen error={this.state.error} />
  }
}

function CrashScreen({ error }: { error: Error }) {
  const save = readRawSave()
  return (
    <div className="crash">
      <h1>The board crashed</h1>
      <p>
        Something in the app threw while drawing the page. Copy your board out first if you need
        it, then clear it — a saved board is the usual cause, and it will crash again on reload
        until it is cleared.
      </p>
      <pre className="crash-error">{errorText(error)}</pre>
      <div className="crash-actions">
        <button onClick={() => void copy(save)} disabled={!save}>
          Copy saved board ({formatSize(save.length)})
        </button>
        <button
          className="crash-danger"
          onClick={() => {
            clearSave()
            location.reload()
          }}
        >
          Clear saved board and reload
        </button>
        <button onClick={() => location.reload()}>Reload</button>
      </div>
      {save && (
        <textarea
          className="crash-save"
          readOnly
          value={save}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
    </div>
  )
}

function formatSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`
}

function errorText(error: Error): string {
  const stack = (error.stack ?? '').split('\n').slice(0, 8).join('\n')
  return stack.includes(error.message) ? stack : `${error.message}\n${stack}`
}

async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard is blocked in some mobile contexts; the textarea below is the fallback.
  }
}
