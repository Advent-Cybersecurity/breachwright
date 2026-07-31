import { Component, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import { ThemeProvider } from './theme';
import Layout from './components/Layout';

const Login = lazy(() => import('./pages/Login'));
const Setup = lazy(() => import('./pages/Setup'));
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

function ProtectedRoute({ children }) {
  const { user, loading, needsSetup } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-accent-red border-t-transparent rounded-full animate-spin" />
          <span className="text-text-muted font-mono text-sm">INITIALIZING</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to={needsSetup ? '/setup' : '/login'} replace />;
  }
  return children;
}

function AppRoutes() {
  const { user, loading, needsSetup } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-red border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route
          path="/setup"
          element={
            user
              ? <Navigate to="/" replace />
              : needsSetup === false
                ? <Navigate to="/login" replace />
                : <Setup />
          }
        />
        <Route
          path="/login"
          element={
            user
              ? <Navigate to="/" replace />
              : needsSetup
                ? <Navigate to="/setup" replace />
                : <Login />
          }
        />
        <Route path="/" element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }>
          <Route index element={<Dashboard />} />
          <Route path="engagements/:id" element={<EngagementDetail />} />
          <Route path="tools" element={<ToolRunner />} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="settings" element={<Settings />} />
          <Route path="knowledge" element={<KnowledgeBase />} />
        </Route>
        <Route
          path="*"
          element={
            <Navigate
              to={user ? '/' : needsSetup ? '/setup' : '/login'}
              replace
            />
          }
        />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <ThemeProvider>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
