'use client';

import React from 'react';

interface SceneErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface SceneErrorBoundaryState {
  hasError: boolean;
  message?: string;
}

export default class SceneErrorBoundary extends React.Component<SceneErrorBoundaryProps, SceneErrorBoundaryState> {
  state: SceneErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(error: Error): SceneErrorBoundaryState {
    return { hasError: true, message: error?.message || 'Unknown runtime error' };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Three scene runtime error:', error, info);
  }

  private reset = () => {
    this.setState({ hasError: false, message: undefined });
  };

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/85 px-6">
          <div className="max-w-xl rounded-lg border border-red-600/50 bg-red-950/40 p-5 text-red-100 space-y-2">
            <h2 className="text-lg font-semibold">Scene failed to render</h2>
            <p className="text-sm text-red-200/90">{this.state.message || 'Unexpected runtime failure.'}</p>
            <button
              onClick={this.reset}
              className="mt-2 rounded bg-red-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-red-400"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
