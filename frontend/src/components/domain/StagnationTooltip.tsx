import type * as React from "react";

/** Tooltip por hover, sem dependência nova (mesma decisão da spec 051 — regra dos 3
 * usos: um popover só pra isto não justifica @radix-ui/react-tooltip ainda). Puro
 * CSS: `group`/`group-hover` do Tailwind. */
export function StagnationTooltip({
  message,
  children,
}: {
  message: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <span className="group relative inline-block">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden w-max max-w-[16rem] -translate-x-1/2 rounded bg-primary px-2 py-1 text-xs text-primary-foreground group-hover:block group-focus-within:block"
      >
        {message}
      </span>
    </span>
  );
}
