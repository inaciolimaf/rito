import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppLayout } from "@/components/shell/AppLayout";
import { ModulePlaceholderPage } from "@/components/shell/ModulePlaceholderPage";
import { NotFoundPage } from "@/components/shell/NotFoundPage";
import { ROUTABLE_NAV_ITEMS } from "@/components/shell/navItems";
import { LoginPage } from "@/features/auth/LoginPage";
import { KitchenSinkPage } from "@/features/kitchen-sink/KitchenSinkPage";
import { useAuth, AuthProvider } from "@/providers/AuthProvider";
import { ThemeProvider } from "@/providers/ThemeProvider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function HomePage(): JSX.Element {
  const { user } = useAuth();
  return <ModulePlaceholderPage title={`Meu Painel — bem-vindo, ${user?.name ?? ""}`} />;
}

export function App(): JSX.Element {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <BrowserRouter>
            <AuthProvider>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                {import.meta.env.DEV && (
                  <Route path="/kitchen-sink" element={<KitchenSinkPage />} />
                )}
                <Route element={<ProtectedRoute />}>
                  <Route element={<AppLayout />}>
                    <Route path="/" element={<Navigate to="/home" replace />} />
                    <Route path="/home" element={<HomePage />} />
                    {ROUTABLE_NAV_ITEMS.filter((item) => item.path !== "/home").map((item) => (
                      <Route
                        key={item.path}
                        path={item.path}
                        element={<ModulePlaceholderPage title={item.label} />}
                      />
                    ))}
                    <Route path="*" element={<NotFoundPage />} />
                  </Route>
                </Route>
              </Routes>
            </AuthProvider>
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
