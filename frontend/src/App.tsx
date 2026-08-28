import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppLayout } from "@/components/shell/AppLayout";
import { ModulePlaceholderPage } from "@/components/shell/ModulePlaceholderPage";
import { NotFoundPage } from "@/components/shell/NotFoundPage";
import { ROUTABLE_NAV_ITEMS } from "@/components/shell/navItems";
import { LoginPage } from "@/features/auth/LoginPage";
import { AuthProvider } from "@/providers/AuthProvider";
import { ThemeProvider } from "@/providers/ThemeProvider";

// Spec 098, regra 7: cada página é um chunk próprio, carregado quando a rota é
// visitada. O que motivou isto é concreto: o editor de modelos carrega o TipTap inteiro
// e os relatórios carregam os gráficos — juntos, dois terços do bundle, para telas que a
// maioria das sessões nunca abre. A tela de login fica estática de propósito: ela é a
// primeira coisa que todo mundo vê, e adiar o carregamento dela seria trocar o problema
// de lugar.
const AccountPage = lazy(async () => ({
  default: (await import("@/features/account/AccountPage")).AccountPage,
}));
const ActionGroupsListPage = lazy(async () => ({
  default: (await import("@/features/action-groups/ActionGroupsListPage")).ActionGroupsListPage,
}));
const AiSettingsPage = lazy(async () => ({
  default: (await import("@/features/ai/AiSettingsPage")).AiSettingsPage,
}));
const ApiTokensPage = lazy(async () => ({
  default: (await import("@/features/api-tokens/ApiTokensPage")).ApiTokensPage,
}));
const AutomationsSettingsPage = lazy(async () => ({
  default: (await import("@/features/automations/AutomationsSettingsPage")).AutomationsSettingsPage,
}));
const CalendarPage = lazy(async () => ({
  default: (await import("@/features/schedule/CalendarPage")).CalendarPage,
}));
const CrmPage = lazy(async () => ({ default: (await import("@/features/crm/CrmPage")).CrmPage }));
const CustomerListPage = lazy(async () => ({
  default: (await import("@/features/customers/CustomerListPage")).CustomerListPage,
}));
const CustomerOriginsListPage = lazy(async () => ({
  default: (await import("@/features/customer-origins/CustomerOriginsListPage"))
    .CustomerOriginsListPage,
}));
const FinancialSettingsPage = lazy(async () => ({
  default: (await import("@/features/financial/FinancialSettingsPage")).FinancialSettingsPage,
}));
const GoalsSettingsPage = lazy(async () => ({
  default: (await import("@/features/taskscore/GoalsSettingsPage")).GoalsSettingsPage,
}));
const InboxPage = lazy(async () => ({
  default: (await import("@/features/inbox/InboxPage")).InboxPage,
}));
const IntegrationsSettingsPage = lazy(async () => ({
  default: (await import("@/features/integrations/IntegrationsSettingsPage"))
    .IntegrationsSettingsPage,
}));
const KitchenSinkPage = lazy(async () => ({
  default: (await import("@/features/kitchen-sink/KitchenSinkPage")).KitchenSinkPage,
}));
const LawsuitDetailPage = lazy(async () => ({
  default: (await import("@/features/lawsuits/LawsuitDetailPage")).LawsuitDetailPage,
}));
const LawsuitTypesListPage = lazy(async () => ({
  default: (await import("@/features/lawsuit-types/LawsuitTypesListPage")).LawsuitTypesListPage,
}));
const LawsuitsPage = lazy(async () => ({
  default: (await import("@/features/lawsuits/LawsuitsPage")).LawsuitsPage,
}));
const MonitoredTermsListPage = lazy(async () => ({
  default: (await import("@/features/monitored-terms/MonitoredTermsListPage"))
    .MonitoredTermsListPage,
}));
const NotificationSettingsPage = lazy(async () => ({
  default: (await import("@/features/notifications/NotificationSettingsPage"))
    .NotificationSettingsPage,
}));
const PartnersPage = lazy(async () => ({
  default: (await import("@/features/partners/PartnersPage")).PartnersPage,
}));
const PostDetailPage = lazy(async () => ({
  default: (await import("@/features/posts/PostDetailPage")).PostDetailPage,
}));
const PublicationListPage = lazy(async () => ({
  default: (await import("@/features/publications/PublicationListPage")).PublicationListPage,
}));
const ReportsPage = lazy(async () => ({
  default: (await import("@/features/reports/ReportsPage")).ReportsPage,
}));
const StagesListPage = lazy(async () => ({
  default: (await import("@/features/stages/StagesListPage")).StagesListPage,
}));
const TaskTypesListPage = lazy(async () => ({
  default: (await import("@/features/task-types/TaskTypesListPage")).TaskTypesListPage,
}));
const TemplateEditorPage = lazy(async () => ({
  default: (await import("@/features/templates/TemplateEditorPage")).TemplateEditorPage,
}));
const TemplatesListPage = lazy(async () => ({
  default: (await import("@/features/templates/TemplatesListPage")).TemplatesListPage,
}));
const TransactionsListPage = lazy(async () => ({
  default: (await import("@/features/financial/TransactionsListPage")).TransactionsListPage,
}));
const UserDetailPage = lazy(async () => ({
  default: (await import("@/features/users/UserDetailPage")).UserDetailPage,
}));
const UsersSettingsPage = lazy(async () => ({
  default: (await import("@/features/users/UsersSettingsPage")).UsersSettingsPage,
}));
const WebhooksSettingsPage = lazy(async () => ({
  default: (await import("@/features/webhooks/WebhooksSettingsPage")).WebhooksSettingsPage,
}));
const WorkflowsListPage = lazy(async () => ({
  default: (await import("@/features/workflows/WorkflowsListPage")).WorkflowsListPage,
}));

/** Enquanto o chunk da rota chega. O shell (sidebar, header) já está na tela — o que
 * pisca é só a área de conteúdo, e um vazio é menos ruidoso que um spinner que aparece
 * por 80 ms numa rede boa. */
function CarregandoRota(): JSX.Element {
  return <div className="p-6" aria-busy="true" />;
}

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
              <Suspense fallback={<CarregandoRota />}>
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
                      <Route path="/settings/automations" element={<AutomationsSettingsPage />} />
                      <Route path="/settings/webhooks" element={<WebhooksSettingsPage />} />
                      <Route path="/settings/api" element={<ApiTokensPage />} />
                      <Route path="/settings/goals" element={<GoalsSettingsPage />} />
                      {/* Atalho legado do widget de meta (spec 028 aponta para /goals). */}
                      <Route path="/goals" element={<Navigate to="/settings/goals" replace />} />
                      <Route path="/settings/origins" element={<CustomerOriginsListPage />} />
                      <Route
                        path="/settings/monitored-terms"
                        element={<MonitoredTermsListPage />}
                      />
                      <Route path="/settings/integrations" element={<IntegrationsSettingsPage />} />
                      <Route path="/settings/ai" element={<AiSettingsPage />} />
                      <Route path="/settings/financial" element={<FinancialSettingsPage />} />
                      <Route
                        path="/settings/notifications"
                        element={<NotificationSettingsPage />}
                      />
                      <Route path="/customers" element={<CustomerListPage />} />
                      <Route path="/lawsuits" element={<LawsuitsPage />} />
                      <Route path="/lawsuits/:id" element={<LawsuitDetailPage />} />
                      <Route path="/posts/:id" element={<PostDetailPage />} />
                      <Route path="/schedules" element={<CalendarPage />} />
                      <Route path="/publications" element={<PublicationListPage />} />
                      <Route path="/crm" element={<CrmPage />} />
                      <Route path="/partners" element={<PartnersPage />} />
                      <Route path="/transactions" element={<TransactionsListPage />} />
                      <Route path="/library" element={<TemplatesListPage />} />
                      <Route path="/library/:id" element={<TemplateEditorPage />} />
                      <Route path="/reports" element={<ReportsPage />} />
                      {ROUTABLE_NAV_ITEMS.filter(
                        (item) =>
                          item.path !== "/home" &&
                          item.path !== "/subscription/account" &&
                          item.path !== "/customers" &&
                          item.path !== "/lawsuits" &&
                          item.path !== "/schedules" &&
                          item.path !== "/publications" &&
                          item.path !== "/crm" &&
                          item.path !== "/partners" &&
                          item.path !== "/transactions" &&
                          item.path !== "/library" &&
                          item.path !== "/reports",
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
              </Suspense>
            </AuthProvider>
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
