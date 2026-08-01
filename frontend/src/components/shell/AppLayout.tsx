import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { Header } from "@/components/shell/Header";
import { Sidebar } from "@/components/shell/Sidebar";
import { cn } from "@/lib/utils";

export function AppLayout(): JSX.Element {
  const location = useLocation();
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = React.useState(false);
  const [placeholderModalLabel, setPlaceholderModalLabel] = React.useState<string | null>(null);

  React.useEffect(() => {
    setIsMobileDrawerOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex h-screen flex-col md:flex-row">
      <div className="hidden md:block">
        <Sidebar onOpenPlaceholderModal={setPlaceholderModalLabel} />
      </div>

      {isMobileDrawerOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div
            className="fixed inset-0 bg-primary/50"
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
        <Header onToggleMobileSidebar={() => setIsMobileDrawerOpen((current) => !current)} />
        <div className="border-b border-default px-4 py-2">
          <Breadcrumbs />
        </div>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>

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
