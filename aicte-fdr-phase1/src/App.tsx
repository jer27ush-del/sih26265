import { Suspense, lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth';
import { RequireAuth, RequireRole } from './routes/guards';
import { Layout } from './components/Layout';
import { LoginPage } from './features/LoginPage';
import { DashboardPage } from './features/DashboardPage';
import { WorkspacePage } from './features/WorkspacePage';
import './i18n';
import './styles.css';

const InstitutionsPage = lazy(async () =>
  import('./features/institutions/InstitutionsPage').then((module) => ({
    default: module.InstitutionsPage,
  })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense
            fallback={<div className="route-loading" role="status">Loading module…</div>}
          >
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<Layout />}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route element={<RequireRole roles={['administrator']} />}>
                    <Route path="/institutions" element={<InstitutionsPage />} />
                  </Route>
                  <Route path="/fdrs" element={<WorkspacePage />} />
                  <Route path="/register" element={<WorkspacePage />} />
                  <Route path="/verification" element={<WorkspacePage />} />
                  <Route path="/maturity" element={<WorkspacePage />} />
                  <Route path="/release" element={<WorkspacePage />} />
                  <Route path="/reports" element={<WorkspacePage />} />
                  <Route path="/notifications" element={<WorkspacePage />} />
                  <Route path="/audit" element={<WorkspacePage />} />
                  <Route path="/settings" element={<WorkspacePage />} />
                </Route>
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
