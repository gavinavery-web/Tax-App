import React from "react";
import { toast } from "sonner";

// ErrorBoundary — catches any uncaught render error and shows a friendly
// amber card instead of React's red runtime overlay. Logs to console for
// debugging.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info);
    try {
      toast.error("Something went wrong — the page was caught safely.");
    } catch (e) { /* sonner not mounted yet, ignore */ }
  }

  reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 max-w-2xl mx-auto" data-testid="error-boundary">
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-sm">
            <div className="font-semibold text-amber-900 mb-1">A problem occurred on this page</div>
            <div className="text-sm text-amber-800 mb-3 mono">
              {this.state.error?.message || "Unknown error"}
            </div>
            <button
              onClick={() => { this.reset(); window.location.reload(); }}
              className="px-3 py-1.5 bg-zinc-900 text-white text-sm rounded-sm hover:bg-zinc-800"
              data-testid="error-boundary-reload"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
