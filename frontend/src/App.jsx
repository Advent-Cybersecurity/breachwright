import { Component, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './theme';
import Layout from './components/Layout';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const EngagementDetail = lazy(() => import('./pages/EngagementDetail'));
const ToolRunner = lazy(() => import('./pages/ToolRunner'));
const Assistant = lazy(() => import('./pages/Assistant'));
const Settings = lazy(() => import('./pages/Settings'));
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase'));

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, details) {
    console.error('Breachwright interface error', error, details);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center p-6">
        <div className="card max-w-md p-6 text-center" role="alert">
          <h1 className="text-xl font-semibold themed-text-primary mb-2">
            The interface could not finish loading
          </h1>
          <p className="text-sm themed-text-muted mb-5">
            Your saved data is unaffected. Reload the application to try again.
          </p>
          <button
            type="button"
            className="btn-primary"
            onClick={() => window.location.reload()}
          >
            Reload Breachwright
          </button>
        </div>
      </div>
    );
  }
}

function PageLoader() {
  return (
    <div
      className="min-h-screen bg-surface-900 flex items-center justify-center"
      role="status"
      aria-label="Loading page"
    >
      <div className="w-8 h-8 border-2 border-accent-red border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="engagements/:id" element={<EngagementDetail />} />
          <Route path="tools" element={<ToolRunner />} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="settings" element={<Settings />} />
          <Route path="knowledge" element={<KnowledgeBase />} />
        </Route>
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/setup" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <ThemeProvider>
          <AppRoutes />
        </ThemeProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
