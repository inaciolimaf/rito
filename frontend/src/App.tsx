import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppLayout } from "@/components/shell/AppLayout";
import { ModulePlaceholderPage } from "@/components/shell/ModulePlaceholderPage";
import { NotFoundPage } from "@/components/shell/NotFoundPage";
import { ROUTABLE_NAV_ITEMS } from "@/components/shell/navItems";
import { AccountPage } from "@/features/account/AccountPage";
import { ActionGroupsListPage } from "@/features/action-groups/ActionGroupsListPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { KitchenSinkPage } from "@/features/kitchen-sink/KitchenSinkPage";
import { LawsuitTypesListPage } from "@/features/lawsuit-types/LawsuitTypesListPage";
import { StagesListPage } from "@/features/stages/StagesListPage";
import { UserDetailPage } from "@/features/users/UserDetailPage";
import { UsersSettingsPage } from "@/features/users/UsersSettingsPage";
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
                    <Route path="/subscription/account" element={<AccountPage />} />
                    <Route path="/settings/users" element={<UsersSettingsPage />} />
                    <Route path="/settings/users/:id" element={<UserDetailPage />} />
                    <Route path="/settings/action-groups" element={<ActionGroupsListPage />} />
                    <Route path="/settings/lawsuit-types" element={<LawsuitTypesListPage />} />
                    <Route path="/settings/stages" element={<StagesListPage />} />
                    {ROUTABLE_NAV_ITEMS.filter(
                      (item) => item.path !== "/home" && item.path !== "/subscription/account",
                    ).map((item) => (
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
