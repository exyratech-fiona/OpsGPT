import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Catches uncaught render errors anywhere below it so a single broken component
 * shows a recoverable message instead of a blank white screen. Without this, an
 * exception in any child unmounts the whole React tree.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // No external error sink yet (Sentry is a P1 item); log to the console with
    // component stack so issues are at least diagnosable from the browser.
    // eslint-disable-next-line no-console
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#0e1120] p-8 text-center text-slate-200">
        <div className="text-lg font-semibold">Something went wrong</div>
        <p className="max-w-md text-sm text-slate-400">
          An unexpected error occurred while rendering this view. Your data is safe — try reloading.
        </p>
        <pre className="max-w-lg overflow-auto rounded-lg bg-black/40 p-3 text-left text-[11px] text-rose-300">
          {this.state.error.message}
        </pre>
        <div className="flex gap-2">
          <button onClick={this.reset} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800">
            Try again
          </button>
          <button onClick={() => window.location.reload()} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500">
            Reload page
          </button>
        </div>
      </div>
    );
  }
}
