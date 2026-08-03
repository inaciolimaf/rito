import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  DEFAULT_SECTION_ORDER,
  INBOX_SECTION_LABELS,
  type InboxSectionKey,
} from "@/features/inbox/api";

export interface InboxSettingsFormProps {
  initialOrder: InboxSectionKey[];
  onSave: (order: InboxSectionKey[]) => Promise<void>;
}

/** Configuração da ordem das seções (spec 036 §6): arrastar reordena; salvar persiste
 * por usuário (regra 9). Drag & drop nativo do HTML5 — sem dependência nova. */
export function InboxSettingsForm({ initialOrder, onSave }: InboxSettingsFormProps): JSX.Element {
  const [order, setOrder] = React.useState<InboxSectionKey[]>(initialOrder);
  const [saving, setSaving] = React.useState(false);
  const dragIndex = React.useRef<number | null>(null);

  function handleDrop(targetIndex: number): void {
    const from = dragIndex.current;
    dragIndex.current = null;
    if (from === null || from === targetIndex) {
      return;
    }
    setOrder((current) => {
      const next = [...current];
      const [moved] = next.splice(from, 1);
      next.splice(targetIndex, 0, moved ?? "others");
      return next;
    });
  }

  async function handleSave(): Promise<void> {
    setSaving(true);
    try {
      await onSave(order);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">Arraste para reordenar as seções da caixa de entrada.</p>
      <ul className="space-y-1" aria-label="Ordem das seções">
        {order.map((section, index) => (
          <li
            key={section}
            draggable
            onDragStart={() => {
              dragIndex.current = index;
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => handleDrop(index)}
            className="cursor-grab rounded border border-default bg-surface px-3 py-2 text-sm text-primary"
          >
            ⠿ {INBOX_SECTION_LABELS[section]}
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button size="sm" disabled={saving} onClick={() => void handleSave()}>
          Salvar ordem
        </Button>
        <Button size="sm" variant="outline" onClick={() => setOrder(DEFAULT_SECTION_ORDER)}>
          Restaurar padrão
        </Button>
      </div>
    </div>
  );
}
