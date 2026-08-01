import { ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { ROUTABLE_NAV_ITEMS } from "@/components/shell/navItems";

export function Breadcrumbs(): JSX.Element {
  const location = useLocation();
  const current = ROUTABLE_NAV_ITEMS.find((item) => location.pathname.startsWith(item.path));

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-muted">
      <Link to="/home" className="hover:text-primary">
        Início
      </Link>
      {current && current.path !== "/home" && (
        <>
          <ChevronRight className="h-3 w-3" aria-hidden="true" />
          <span aria-current="page" className="text-primary">
            {current.label}
          </span>
        </>
      )}
    </nav>
  );
}
