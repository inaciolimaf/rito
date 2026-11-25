import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/domain/EmptyState";
import { IntegrationAlertBanner } from "@/components/domain/IntegrationAlertBanner";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { Header } from "@/components/shell/Header";
import { Sidebar } from "@/components/shell/Sidebar";
import { requiredCapabilityFor } from "@/components/shell/navItems";
import { useRouteFocus } from "@/components/shell/useRouteFocus";
import { NewTaskModal } from "@/features/posts/NewTaskModal";
import { cn } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

export function AppLayout(): JSX.Element {
  const location = useLocation();
  const { user } = useAuth();
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = React.useState(false);
  const [placeholderModalLabel, setPlaceholderModalLabel] = React.useState<string | null>(null);
  const [taskModalOpen, setTaskModalOpen] = React.useState(false);
  const mainRef = React.useRef<HTMLElement>(null);
  const drawerRef = React.useRef<HTMLDivElement>(null);
  useRouteFocus(mainRef);

  React.useEffect(() => {
    setIsMobileDrawerOpen(false);
  }, [location.pathname]);

  const required = requiredCapabilityFor(location.pathname);
  const deniedCapability = required !== null && !(user?.capabilities ?? []).includes(required);

  // Ao abrir o drawer, o foco vai para o primeiro link dele: sem isso o Escape não chega a ele.
  React.useEffect(() => {
    if (isMobileDrawerOpen) {
      drawerRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    }
  }, [isMobileDrawerOpen]);

  return (
    <div className="flex h-dvh flex-col md:flex-row">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-accent"
      >
        Pular para o conteúdo
      </a>
      <div className="hidden md:block">
        <Sidebar onOpenPlaceholderModal={setPlaceholderModalLabel} />
      </div>

      {isMobileDrawerOpen && (
        <div
          ref={drawerRef}
          className="fixed inset-0 z-40 flex md:hidden"
          onKeyDown={(event) => {
            if (event.key === "Escape") setIsMobileDrawerOpen(false);
          }}
        >
          <div
            className="fixed inset-0 bg-overlay/50"
            onClick={() => setIsMobileDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="relative z-50">
            <Sidebar
              onNavigate={() => setIsMobileDrawerOpen(false)}
              onOpenPlaceholderModal={(label) => {
                setPlaceholderModalLabel(label);
                setIsMobileDrawerOpen(false);
              }}
            />
          </div>
        </div>
      )}

      <div className={cn("flex min-w-0 flex-1 flex-col")}>
        <Header
          onToggleMobileSidebar={() => setIsMobileDrawerOpen((current) => !current)}
          onNewTask={() => setTaskModalOpen(true)}
        />
        <IntegrationAlertBanner />
        <div className="border-b border-default px-4 py-2">
          <Breadcrumbs />
        </div>
        <main
          id="conteudo"
          ref={mainRef}
          tabIndex={-1}
          className="flex-1 overflow-y-auto p-6 focus:outline-none"
        >
          {/* Spec 138, regra 9: o estado "sem permissão" que a spec 006 exige de toda
              tela. Fica aqui, dentro do shell, e não no `ProtectedRoute`: quem cai numa
              área a que não tem acesso precisa continuar com o menu ao lado para ir a
              outro lugar — expulsar da casca deixaria a pessoa sem saída. */}
          {deniedCapability ? (
            <EmptyState
              role="alert"
              title="Você não tem acesso a esta área."
              description="Seu perfil não permite abrir esta tela. Peça a um gestor do escritório para liberar."
            />
          ) : (
            <Outlet />
          )}
        </main>
      </div>

      <NewTaskModal open={taskModalOpen} onOpenChange={setTaskModalOpen} />

      <Dialog
        open={placeholderModalLabel !== null}
        onOpenChange={(open) => !open && setPlaceholderModalLabel(null)}
      >
        <DialogContent>
          <DialogTitle>{placeholderModalLabel}</DialogTitle>
          <DialogDescription>Em breve.</DialogDescription>
        </DialogContent>
      </Dialog>
    </div>
  );
}
