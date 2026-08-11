import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { CancelledBadge } from "@/features/publications/CancelledBadge";
import { getPublication, markPublicationRead } from "@/features/publications/api";

export interface PublicationDetailDrawerProps {
  publicationId: string | null;
  onOpenChange: (open: boolean) => void;
}

/** Regra 4 (spec 048): inteiro teor abre num painel lateral, sem sair da lista —
 * reaproveita o `Dialog` da spec 007 posicionado como drawer (regra dos 3 usos ainda
 * não bateu pra justificar um primitivo de drawer novo). Abrir marca como lida
 * (regra 5, por usuário). */
export function PublicationDetailDrawer({
  publicationId,
  onOpenChange,
}: PublicationDetailDrawerProps): JSX.Element {
  const queryClient = useQueryClient();
  const isOpen = publicationId !== null;

  const { data: publication, isLoading } = useQuery({
    queryKey: ["publications", "detail", publicationId],
    queryFn: () => getPublication(publicationId as string),
    enabled: isOpen,
  });

  React.useEffect(() => {
    if (!publicationId || !publication || publication.is_read) return;
    void markPublicationRead(publicationId).then(() => {
      void queryClient.invalidateQueries({ queryKey: ["publications"] });
    });
    // Só quando o drawer abre com um documento carregado — não a cada refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [publicationId, publication?.id]);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="inset-y-0 left-auto right-0 top-0 h-full max-h-full w-full max-w-md -translate-x-0 -translate-y-0 overflow-y-auto rounded-none">
        <DialogTitle>Inteiro teor</DialogTitle>

        {isLoading && <p className="mt-4 text-sm text-muted">Carregando…</p>}

        {publication && (
          <div className="mt-4 space-y-4 text-sm">
            <dl className="grid grid-cols-2 gap-2">
              <div>
                <dt className="text-muted">Disponibilização</dt>
                <dd>{new Date(publication.availability_date).toLocaleDateString("pt-BR")}</dd>
              </div>
              <div>
                <dt className="text-muted">Tribunal</dt>
                <dd>{publication.court_code}</dd>
              </div>
              <div>
                <dt className="text-muted">Órgão</dt>
                <dd>{publication.organ_name ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-muted">Processo</dt>
                <dd>{publication.process_number ?? "—"}</dd>
              </div>
            </dl>

            {!publication.is_active && <CancelledBadge reason={publication.cancellation_reason} />}

            {publication.recipients.length > 0 && (
              <div>
                <h3 className="font-medium text-primary">Partes</h3>
                <ul className="list-disc pl-5">
                  {publication.recipients.map((recipient, index) => (
                    <li key={index}>{recipient.name}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h3 className="font-medium text-primary">Inteiro teor</h3>
              <p className="whitespace-pre-wrap text-primary">{publication.body}</p>
            </div>

            {publication.link && (
              <a
                href={publication.link}
                target="_blank"
                rel="noreferrer"
                className="text-accent underline"
              >
                Abrir no site do tribunal
              </a>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
