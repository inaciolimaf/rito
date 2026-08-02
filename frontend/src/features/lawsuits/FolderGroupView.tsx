import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { EmptyState } from "@/components/domain/EmptyState";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { listLawsuitGroups, renameLawsuitFolder, type FolderGroup } from "@/features/lawsuits/api";
import { FolderAutocomplete } from "@/features/lawsuits/FolderAutocomplete";
import { ApiError } from "@/lib/errors";
import { formatCnj } from "@/lib/cnj";

const NO_FOLDER_LABEL = "Sem pasta";

/** Renomear em lote dentro da visão agrupada (regras 3–4): um dialog com o mesmo
 * autocomplete do formulário; se o alvo já existe, o 409 vira ConfirmDialog de fusão. */
function RenameFolderDialog({
  group,
  onClose,
  onRenamed,
}: {
  group: FolderGroup;
  onClose: () => void;
  onRenamed: () => void;
}): JSX.Element {
  const [newName, setNewName] = React.useState(group.name);
  const [mergeTarget, setMergeTarget] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  async function submit(merge: boolean): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      await renameLawsuitFolder(group.name, newName, merge);
      onRenamed();
      onClose();
    } catch (submitError) {
      if (submitError instanceof ApiError && submitError.status === 409) {
        setMergeTarget(newName);
      } else {
        setError(submitError instanceof ApiError ? submitError.message : "Erro ao renomear.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent>
          <DialogTitle>Renomear pasta</DialogTitle>
          <DialogDescription>
            Os {group.count} processos de “{group.name}” passam para o novo nome.
          </DialogDescription>
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void submit(false);
            }}
          >
            <FolderAutocomplete
              id="rename-folder"
              value={newName}
              onChange={setNewName}
              placeholder="Novo nome da pasta"
            />
            {error && <p className="text-sm text-danger">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancelar
              </Button>
              <Button type="submit" disabled={submitting || newName.trim() === ""}>
                Renomear
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={mergeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setMergeTarget(null);
        }}
        title="Fundir pastas?"
        description={`Já existe a pasta “${mergeTarget}”. Renomear vai fundir as duas — os processos das duas pastas ficam juntos.`}
        confirmLabel="Fundir"
        onConfirm={() => void submit(true)}
      />
    </>
  );
}

/** Visão agrupada por pasta (spec 029 §6): grupos por contagem decrescente, primeiros
 * processos de cada grupo e atalho para a listagem filtrada. */
export function FolderGroupView(): JSX.Element {
  const queryClient = useQueryClient();
  const [renaming, setRenaming] = React.useState<FolderGroup | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["lawsuits-groups"],
    queryFn: listLawsuitGroups,
  });

  if (isLoading) {
    return <p className="text-sm text-muted">Carregando pastas…</p>;
  }

  const groups = data?.groups ?? [];
  if (groups.length === 0) {
    return (
      <EmptyState
        title="Nenhum processo cadastrado ainda"
        description="Cadastre o primeiro processo do escritório para organizá-lo em pastas."
      />
    );
  }

  async function handleRenamed(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["lawsuits-groups"] });
    await queryClient.invalidateQueries({ queryKey: ["lawsuits-list"] });
    await queryClient.invalidateQueries({ queryKey: ["lawsuits", "stats"] });
  }

  return (
    <div className="space-y-4" data-testid="folder-group-view">
      {groups.map((group) => (
        <section
          key={group.name}
          aria-label={`Pasta ${group.name}`}
          className="rounded border border-default bg-surface"
        >
          <header className="flex items-center justify-between border-b border-default px-4 py-2">
            <h2 className="text-sm font-medium text-primary">
              {group.name} <span className="text-muted">({group.count})</span>
            </h2>
            <div className="flex items-center gap-3">
              {group.name !== NO_FOLDER_LABEL && (
                <>
                  <Link
                    to={`/lawsuits?folder=${encodeURIComponent(group.name)}`}
                    className="text-sm text-accent underline"
                  >
                    Ver todos
                  </Link>
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => setRenaming(group)}
                  >
                    Renomear
                  </button>
                </>
              )}
            </div>
          </header>
          <ul className="divide-y divide-default">
            {group.items.map((item) => (
              <li key={item.id}>
                <Link
                  to={`/lawsuits/${item.id}`}
                  className="flex items-center justify-between px-4 py-2 text-sm hover:bg-surface-muted"
                >
                  <span className="text-primary">
                    {item.process_number ? formatCnj(item.process_number) : "Sem número"}
                  </span>
                  <span className="text-muted">
                    {new Date(item.created_at).toLocaleDateString("pt-BR")}
                  </span>
                </Link>
              </li>
            ))}
            {group.items.length === 0 && (
              <li className="px-4 py-2 text-sm text-muted">Nenhum processo nesta pasta.</li>
            )}
          </ul>
        </section>
      ))}

      {renaming && (
        <RenameFolderDialog
          group={renaming}
          onClose={() => setRenaming(null)}
          onRenamed={() => void handleRenamed()}
        />
      )}
    </div>
  );
}
