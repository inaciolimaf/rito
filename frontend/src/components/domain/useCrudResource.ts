import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ApiError } from "@/lib/errors";

export interface UseCrudResourceOptions<TItem, TFormValues> {
  /** Chave de invalidação do React Query — a mesma usada no `useQuery` da listagem. */
  queryKey: unknown[];
  create: (values: TFormValues) => Promise<TItem>;
  update: (item: TItem, values: TFormValues) => Promise<TItem>;
  remove: (item: TItem) => Promise<void>;
}

export interface UseCrudResourceResult<TItem, TFormValues> {
  editing: TItem | null;
  modalOpen: boolean;
  setModalOpen: (open: boolean) => void;
  formError: ApiError | null;
  pendingDelete: TItem | null;
  setPendingDelete: (item: TItem | null) => void;
  openCreateModal: () => void;
  openEditModal: (item: TItem) => void;
  handleSubmit: (values: TFormValues) => Promise<void>;
  handleConfirmDelete: () => Promise<void>;
}

/** Extrai o padrão repetido em toda tela de cadastro simples (regra dos 3 usos, spec 020):
 * estado de modal/edição/erro/exclusão pendente + submit e delete com invalidação de query.
 * O mapeamento de payload (ex.: espalhar `is_active` atual no update) fica a cargo de
 * `create`/`update`/`remove`, que cada feature define do seu jeito — o hook só orquestra o
 * ciclo de vida, nunca decide o formato do payload. Fluxos que precisam de um passo extra
 * antes de excluir (ex.: transferência obrigatória) usam `setPendingDelete` diretamente em
 * vez de `handleConfirmDelete`. */
export function useCrudResource<TItem, TFormValues>(
  options: UseCrudResourceOptions<TItem, TFormValues>,
): UseCrudResourceResult<TItem, TFormValues> {
  const queryClient = useQueryClient();
  const [editing, setEditing] = React.useState<TItem | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<TItem | null>(null);

  function openCreateModal(): void {
    setEditing(null);
    setFormError(null);
    setModalOpen(true);
  }

  function openEditModal(item: TItem): void {
    setEditing(item);
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(values: TFormValues): Promise<void> {
    setFormError(null);
    try {
      if (editing) {
        await options.update(editing, values);
      } else {
        await options.create(values);
      }
      setModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: options.queryKey });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    await options.remove(pendingDelete);
    setPendingDelete(null);
    await queryClient.invalidateQueries({ queryKey: options.queryKey });
  }

  return {
    editing,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  };
}
