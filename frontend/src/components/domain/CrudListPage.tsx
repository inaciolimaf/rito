import type * as React from "react";
import type { UseFormReturn } from "react-hook-form";
import type { z } from "zod";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import { TransferBeforeDeleteDialog } from "@/components/domain/TransferBeforeDeleteDialog";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import type { UseCrudResourceResult } from "@/components/domain/useCrudResource";
import type { UseTransferBeforeDeleteResult } from "@/components/domain/useTransferBeforeDelete";
import { ApiError } from "@/lib/errors";

/** Toda tela de cadastro simples lista um registro com identidade e nome — é o nome que
 * aparece na coluna, no diálogo de exclusão e na lista de destinos da transferência. */
export interface CrudNamedItem {
  id: string;
  name: string;
}

export interface CrudTransferConfig<TItem> {
  /** O fluxo de `useTransferBeforeDelete` já instanciado pela feature. */
  flow: UseTransferBeforeDeleteResult<TItem>;
  title: string;
  description: (item: TItem | null) => string;
}

export interface CrudListPageProps<
  TItem extends CrudNamedItem,
  // O mesmo `any` de `FormModal` (spec 007, §9): `z.infer<TSchema>` não funciona sem esse
  // bound, e é o preço de expor um componente genuinamente genérico por schema Zod.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  TSchema extends z.ZodType<any, any, any>,
> {
  title: string;
  /** Rótulo do botão do cabeçalho ("Novo centro de custo"). */
  createLabel: string;
  /** Sem permissão de escrita: some o botão de criar e as ações de linha (regra 4). */
  canWrite: boolean;
  /** Ausente = tela sem barra de filtros (ex.: Times). */
  filterFields?: FilterFieldDef[];
  columns: DataTableColumn<TItem>[];
  data: TItem[];
  isLoading: boolean;
  /** Erro cru do React Query — só `ApiError` vira mensagem na tabela. */
  error: unknown;
  emptyMessage: string;
  crud: UseCrudResourceResult<TItem, z.infer<TSchema>>;
  /** `false` esconde só o botão Excluir da linha (registros padrão do sistema). */
  canDeleteRow?: (row: TItem) => boolean;
  /** Sobrescreve o clique em Excluir. O padrão é marcar o registro como pendente. */
  onDeleteRequest?: (row: TItem) => void;
  createTitle: string;
  editTitle: string;
  schema: TSchema;
  emptyFormValues: z.infer<TSchema>;
  toFormValues: (item: TItem) => z.infer<TSchema>;
  formFields: (form: UseFormReturn<z.infer<TSchema>>) => React.ReactNode;
  confirmTitle: string;
  confirmDescription: (item: TItem | null) => string;
  /** Quando devolve `false`, o registro pendente não abre a confirmação simples — a tela
   * tem outro caminho para ele (grupos de ação abrem a transferência direto). */
  isDeletableWithoutTransfer?: (item: TItem) => boolean;
  /** Padrão: `crud.handleConfirmDelete`, ou o pedido de exclusão do fluxo de
   * transferência quando `transfer` está presente. */
  onConfirmDelete?: () => void | Promise<void>;
  /** Fluxo "transferir antes de excluir" no formato padrão (spec 101, Bloco A). */
  transfer?: CrudTransferConfig<TItem>;
  /** Rodapé livre — diálogos e alertas que fogem do padrão. */
  children?: React.ReactNode;
}

/**
 * Casca das telas de cadastro simples: cabeçalho + filtros + tabela + modal de formulário
 * + confirmação de exclusão (+ transferência antes de excluir, quando existe).
 *
 * O oitavo de `components/domain/`, nascido da spec 119: seis telas — centros de custo,
 * categorias financeiras, origens de pessoa, tipos de ação, times e grupos de ação —
 * repetiam o mesmo bloco linha a linha, o dobro do gatilho da regra dos 3 usos
 * (`CLAUDE.md` §6). A extração é literal: o DOM que cada tela produzia continua o mesmo,
 * e o que variava (rótulos, colunas, permissão, formulário) virou prop.
 *
 * Não faz fetch nem guarda estado: recebe os dados da feature e o ciclo de vida de
 * `useCrudResource`, como manda a regra 1 da spec 007.
 */
export function CrudListPage<
  TItem extends CrudNamedItem,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  TSchema extends z.ZodType<any, any, any>,
>({
  title,
  createLabel,
  canWrite,
  filterFields,
  columns,
  data,
  isLoading,
  error,
  emptyMessage,
  crud,
  canDeleteRow,
  onDeleteRequest,
  createTitle,
  editTitle,
  schema,
  emptyFormValues,
  toFormValues,
  formFields,
  confirmTitle,
  confirmDescription,
  isDeletableWithoutTransfer,
  onConfirmDelete,
  transfer,
  children,
}: CrudListPageProps<TItem, TSchema>): JSX.Element {
  const { editing, pendingDelete, setPendingDelete } = crud;

  function requestDelete(row: TItem): void {
    if (onDeleteRequest) {
      onDeleteRequest(row);
      return;
    }
    setPendingDelete(row);
  }

  async function confirmDelete(): Promise<void> {
    if (onConfirmDelete) {
      await onConfirmDelete();
      return;
    }
    if (!transfer) {
      await crud.handleConfirmDelete();
      return;
    }
    // Com transferência, a confirmação não exclui: ela *tenta* excluir e deixa o 409 do
    // backend decidir se abre o diálogo de destino (ver useTransferBeforeDelete).
    const alvo = pendingDelete;
    if (!alvo) return;
    setPendingDelete(null);
    await transfer.flow.requestDelete(alvo);
  }

  const transferOptions: EntityOption[] = transfer
    ? data
        .filter((item) => item.id !== transfer.flow.pendingTransfer?.id)
        .map((item) => ({ id: item.id, label: item.name }))
    : [];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">{title}</h1>
        {canWrite && <Button onClick={crud.openCreateModal}>{createLabel}</Button>}
      </div>

      {filterFields && <FilterBar fields={filterFields} />}

      <DataTable
        columns={columns}
        data={data}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage={emptyMessage}
        rowActions={
          canWrite
            ? (row) => (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => crud.openEditModal(row)}
                  >
                    Editar
                  </button>
                  {(canDeleteRow?.(row) ?? true) && (
                    <button
                      type="button"
                      className="text-sm text-danger underline"
                      onClick={() => requestDelete(row)}
                    >
                      Excluir
                    </button>
                  )}
                </div>
              )
            : undefined
        }
      />

      <FormModal
        open={crud.modalOpen}
        onOpenChange={crud.setModalOpen}
        title={editing ? editTitle : createTitle}
        schema={schema}
        defaultValues={editing ? toFormValues(editing) : emptyFormValues}
        serverError={crud.formError}
        onSubmit={crud.handleSubmit}
      >
        {(form) => formFields(form)}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null && (isDeletableWithoutTransfer?.(pendingDelete) ?? true)}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title={confirmTitle}
        description={confirmDescription(pendingDelete)}
        confirmLabel="Excluir"
        destructive
        onConfirm={confirmDelete}
      />

      {transfer && (
        <>
          <TransferBeforeDeleteDialog
            open={transfer.flow.dialogOpen}
            onOpenChange={(open) => {
              if (!open) transfer.flow.closeDialog();
            }}
            title={transfer.title}
            description={transfer.description(transfer.flow.pendingTransfer)}
            options={transferOptions}
            onTransfer={transfer.flow.transferAndDelete}
          />
          {transfer.flow.transferError && (
            <p role="alert" className="text-sm text-danger">
              {transfer.flow.transferError.message}
            </p>
          )}
        </>
      )}

      {children}
    </div>
  );
}
