import * as React from "react";
import { useLocation } from "react-router-dom";

import { ROUTABLE_NAV_ITEMS } from "@/components/shell/navItems";

const APP_NAME = "Rito";

/**
 * Ao trocar de tela (WCAG 2.4.2 e 2.4.3): atualiza `document.title` com o nome da tela e move o
 * foco para o `main`, para que o leitor de tela anuncie a tela nova. Na primeira renderização
 * não rouba o foco de ninguém.
 */
export function useRouteFocus(mainRef: React.RefObject<HTMLElement>): void {
  const { pathname } = useLocation();
  const lastPathname = React.useRef(pathname);

  React.useEffect(() => {
    const current = ROUTABLE_NAV_ITEMS.find((item) => pathname.startsWith(item.path));
    document.title = current ? `${current.label} · ${APP_NAME}` : APP_NAME;

    if (lastPathname.current !== pathname) {
      lastPathname.current = pathname;
      mainRef.current?.focus();
    }
  }, [pathname, mainRef]);
}
