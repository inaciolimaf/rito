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
import { MonitoredTermsListPage } from "@/features/monitored-terms/MonitoredTermsListPage";
import { CustomerOriginsListPage } from "@/features/customer-origins/CustomerOriginsListPage";
import { CustomerListPage } from "@/features/customers/CustomerListPage";
import { KitchenSinkPage } from "@/features/kitchen-sink/KitchenSinkPage";
import { LawsuitTypesListPage } from "@/features/lawsuit-types/LawsuitTypesListPage";
import { LawsuitsPage } from "@/features/lawsuits/LawsuitsPage";
import { LawsuitDetailPage } from "@/features/lawsuits/LawsuitDetailPage";
import { InboxPage } from "@/features/inbox/InboxPage";
import { PostDetailPage } from "@/features/posts/PostDetailPage";
import { PublicationListPage } from "@/features/publications/PublicationListPage";
import { CalendarPage } from "@/features/schedule/CalendarPage";
import { StagesListPage } from "@/features/stages/StagesListPage";
import { TaskTypesListPage } from "@/features/task-types/TaskTypesListPage";
import { GoalsSettingsPage } from "@/features/taskscore/GoalsSettingsPage";
import { UserDetailPage } from "@/features/users/UserDetailPage";
import { UsersSettingsPage } from "@/features/users/UsersSettingsPage";
import { WorkflowsListPage } from "@/features/workflows/WorkflowsListPage";
import { AuthProvider } from "@/providers/AuthProvider";
import { ThemeProvider } from "@/providers/ThemeProvider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

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
                    <Route path="/home" element={<InboxPage />} />
                    <Route path="/subscription/account" element={<AccountPage />} />
                    <Route path="/settings/users" element={<UsersSettingsPage />} />
                    <Route path="/settings/users/:id" element={<UserDetailPage />} />
                    <Route path="/settings/action-groups" element={<ActionGroupsListPage />} />
                    <Route path="/settings/lawsuit-types" element={<LawsuitTypesListPage />} />
                    <Route path="/settings/stages" element={<StagesListPage />} />
                    <Route path="/settings/task-types" element={<TaskTypesListPage />} />
                    <Route path="/settings/workflows" element={<WorkflowsListPage />} />
                    <Route path="/settings/goals" element={<GoalsSettingsPage />} />
                    {/* Atalho legado do widget de meta (spec 028 aponta para /goals). */}
                    <Route path="/goals" element={<Navigate to="/settings/goals" replace />} />
                    <Route path="/settings/origins" element={<CustomerOriginsListPage />} />
                    <Route path="/settings/monitored-terms" element={<MonitoredTermsListPage />} />
                    <Route path="/customers" element={<CustomerListPage />} />
                    <Route path="/lawsuits" element={<LawsuitsPage />} />
                    <Route path="/lawsuits/:id" element={<LawsuitDetailPage />} />
                    <Route path="/posts/:id" element={<PostDetailPage />} />
                    <Route path="/schedules" element={<CalendarPage />} />
                    <Route path="/publications" element={<PublicationListPage />} />
                    {ROUTABLE_NAV_ITEMS.filter(
                      (item) =>
                        item.path !== "/home" &&
                        item.path !== "/subscription/account" &&
                        item.path !== "/customers" &&
                        item.path !== "/lawsuits" &&
                        item.path !== "/schedules" &&
                        item.path !== "/publications",
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
