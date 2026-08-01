import { Plus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const QUICK_ADD_ITEMS = [
  { label: "Nova tarefa", path: "/posts" },
  { label: "Novo contato", path: "/customers" },
  { label: "Novo processo", path: "/lawsuits" },
  { label: "Nova receita/despesa", path: "/transactions" },
];

export function QuickAddMenu(): JSX.Element {
  const [isOpen, setIsOpen] = React.useState(false);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <Button
        type="button"
        size="sm"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <Plus className="mr-1 h-4 w-4" />
        Adicionar
      </Button>

      {isOpen && (
        <ul
          role="menu"
          aria-label="Adicionar"
          className="absolute right-0 top-full z-10 mt-1 w-48 rounded border border-default bg-surface py-1 shadow-lg"
        >
          {QUICK_ADD_ITEMS.map((item) => (
            <li key={item.label} role="none">
              <button
                type="button"
                role="menuitem"
                className={cn(
                  "block w-full px-3 py-2 text-left text-sm text-primary hover:bg-surface-muted",
                )}
                onClick={() => {
                  navigate(item.path);
                  setIsOpen(false);
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
