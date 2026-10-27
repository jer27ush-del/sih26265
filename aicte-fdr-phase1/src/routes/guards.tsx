import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../useAuth';
import type { Role } from '../types';

export function RequireAuth() {
  const { user, ready } = useAuth();
  if (!ready) return <div className="route-loading" role="status">Checking your session…</div>;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

export function RequireRole({ roles }: { roles: Role[] }) {
  const { user } = useAuth();
  return user && roles.includes(user.role) ? <Outlet /> : <Navigate to="/dashboard" replace />;
}
