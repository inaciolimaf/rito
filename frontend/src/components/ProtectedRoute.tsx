import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/providers/AuthProvider";

export function ProtectedRoute(): JSX.Element | null {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return null;
  }

  if (!isAuthenticated) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <Outlet />;
}
