import * as React from "react";

import { Button } from "@/components/ui/button";
import { completePost } from "@/features/posts/api";
import { RetroactiveDateField } from "@/features/posts/RetroactiveDateField";

export interface CompleteTaskButtonProps {
  postId: string;
  /** Já concluída pelo usuário atual — o botão some (a linha dele fechou). */
  alreadyCompleted?: boolean;
  onCompleted: () => void;
}

/** Concluir a própria linha da tarefa (spec 033, regra 1): um clique conclui agora;
 * a data retroativa é opcional (regra 4). A caixa de entrada (036) monta este botão
 * por linha. */
export function CompleteTaskButton({
  postId,
  alreadyCompleted = false,
  onCompleted,
}: CompleteTaskButtonProps): JSX.Element | null {
  const [retroDate, setRetroDate] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  if (alreadyCompleted) return null;

  async function handleComplete(): Promise<void> {
    setSubmitting(true);
    try {
      await completePost(postId, retroDate ? `${retroDate}T12:00:00Z` : undefined);
      onCompleted();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex items-end gap-2">
      <Button type="button" size="sm" disabled={submitting} onClick={() => void handleComplete()}>
        Concluir
      </Button>
      <RetroactiveDateField value={retroDate} onChange={setRetroDate} />
    </div>
  );
}
