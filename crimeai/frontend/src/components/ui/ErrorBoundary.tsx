import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

interface State {
  error: Error | null
}

/** Contains a crashing page so the rest of the app (navigation, alerts) keeps working. */
export default class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page crashed', error, info.componentStack)
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md text-center">
          <AlertTriangle size={28} className="mx-auto text-severity-medium" />
          <h2 className="mt-3 text-sm font-semibold text-text-primary">This view hit an error</h2>
          <p className="mt-1 text-xs text-text-secondary">{this.state.error.message}</p>
          <button type="button" onClick={() => this.setState({ error: null })} className="btn-secondary mt-4 text-xs">
            <RotateCcw size={13} /> Try again
          </button>
        </div>
      </div>
    )
  }
}
