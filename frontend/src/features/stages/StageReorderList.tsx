import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import * as React from "react";

import type { StageData } from "@/features/stages/api";
import { cn } from "@/lib/utils";

export interface StageReorderListProps {
  stages: StageData[];
  onReorder: (orderedIds: string[]) => Promise<void>;
}

/** Lista de etapas de uma única fase, arrastável (regra 5: `position` dentro da fase). Os
 * botões de mover para cima/baixo cobrem o mesmo caso de uso por teclado — arrastar sozinho
 * não é operável sem mouse. */
export function StageReorderList({ stages, onReorder }: StageReorderListProps): JSX.Element {
  const [order, setOrder] = React.useState<StageData[]>(stages);
  const dragIndex = React.useRef<number | null>(null);

  React.useEffect(() => {
    setOrder(stages);
  }, [stages]);

  function move(from: number, to: number): void {
    if (to < 0 || to >= order.length) return;
    const next = [...order];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    next.splice(to, 0, moved);
    setOrder(next);
    void onReorder(next.map((stage) => stage.id));
  }

  return (
    <ul className="flex flex-col gap-1" aria-label="Etapas desta fase, em ordem">
      {order.map((stage, index) => (
        <li
          key={stage.id}
          draggable
          onDragStart={() => {
            dragIndex.current = index;
          }}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            if (dragIndex.current !== null && dragIndex.current !== index) {
              move(dragIndex.current, index);
            }
            dragIndex.current = null;
          }}
          className={cn(
            "flex items-center justify-between gap-2 rounded border border-default bg-surface px-3 py-2",
          )}
        >
          <span className="flex items-center gap-2 text-sm text-primary">
            <GripVertical className="h-4 w-4 text-muted" aria-hidden="true" />
            {stage.name}
          </span>
          <span className="flex gap-1">
            <button
              type="button"
              aria-label={`Mover ${stage.name} para cima`}
              className="rounded p-1 text-muted hover:text-primary disabled:opacity-30"
              disabled={index === 0}
              onClick={() => move(index, index - 1)}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label={`Mover ${stage.name} para baixo`}
              className="rounded p-1 text-muted hover:text-primary disabled:opacity-30"
              disabled={index === order.length - 1}
              onClick={() => move(index, index + 1)}
            >
              <ArrowDown className="h-4 w-4" />
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}
