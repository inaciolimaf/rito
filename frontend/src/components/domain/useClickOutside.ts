import * as React from "react";

/** Fechar ao clicar fora **e** ao apertar Esc — spec 138, regra 10.
 *
 * Estava copiado em quatro componentes (`EntityPicker`, `QuickAddMenu`,
 * `NotificationBell`, o menu de usuário do `Header`), um a mais que a regra dos 3 usos
 * permite. E só uma das cópias tratava `Escape`, apesar de as três do shell anunciarem
 * `role="menu"` — quem navega por teclado abria o menu e não conseguia fechá-lo. */
export function useClickOutside<TElement extends HTMLElement>(
  isOpen: boolean,
  onClose: () => void,
): React.RefObject<TElement> {
  const ref = React.useRef<TElement>(null);

  React.useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(event: MouseEvent): void {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose();
      }
    }
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  return ref;
}
