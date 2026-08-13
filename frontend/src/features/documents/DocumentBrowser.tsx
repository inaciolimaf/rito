import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { EmptyState } from "@/components/domain/EmptyState";
import { Button } from "@/components/ui/button";
import {
  createDocumentFolder,
  deleteDocument,
  deleteDocumentFolder,
  getDocumentDownloadUrl,
  listDocuments,
  searchDocuments,
  uploadDocuments,
  type DocumentData,
  type DocumentFolderData,
  type DocumentScopeType,
  type DocumentSortField,
  type DocumentSortOrder,
} from "@/features/documents/api";
import { ApiError } from "@/lib/errors";

export interface DocumentBrowserProps {
  scopeType: DocumentScopeType;
  scopeId: string;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return date.toLocaleDateString("pt-BR");
}

/** Nuvem de documentos por contato/processo (spec 063) — não usa `DataTable`: pasta e
 * documento são linhas de tipos diferentes, o contrato de listagem espera uma linha
 * homogênea (§6). */
export function DocumentBrowser({ scopeType, scopeId }: DocumentBrowserProps): JSX.Element {
  const queryClient = useQueryClient();
  const [folderStack, setFolderStack] = React.useState<DocumentFolderData[]>([]);
  const currentFolderId = folderStack.at(-1)?.id ?? null;
  const [sort, setSort] = React.useState<DocumentSortField>("name");
  const [order, setOrder] = React.useState<DocumentSortOrder>("asc");
  const [search, setSearch] = React.useState("");
  const [newFolderName, setNewFolderName] = React.useState("");
  const [creatingFolder, setCreatingFolder] = React.useState(false);
  const [pendingDeleteDocument, setPendingDeleteDocument] = React.useState<DocumentData | null>(
    null,
  );
  const [pendingDeleteFolder, setPendingDeleteFolder] = React.useState<DocumentFolderData | null>(
    null,
  );
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const listQuery = useQuery({
    queryKey: ["documents", scopeType, scopeId, currentFolderId, sort, order],
    queryFn: () =>
      listDocuments({
        scope_type: scopeType,
        scope_id: scopeId,
        folder_id: currentFolderId,
        sort,
        order,
      }),
    enabled: search.trim() === "",
  });

  const searchQuery = useQuery({
    queryKey: ["documents-search", scopeType, scopeId, search],
    queryFn: () => searchDocuments(scopeType, scopeId, search.trim()),
    enabled: search.trim() !== "",
  });

  const isSearching = search.trim() !== "";
  const folders = isSearching ? [] : (listQuery.data?.folders ?? []);
  const documents = isSearching ? (searchQuery.data ?? []) : (listQuery.data?.documents ?? []);
  const isLoading = isSearching ? searchQuery.isLoading : listQuery.isLoading;

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["documents", scopeType, scopeId] });
    void queryClient.invalidateQueries({ queryKey: ["documents-search", scopeType, scopeId] });
    void queryClient.invalidateQueries({ queryKey: ["account-storage"] });
  }

  const upload = useMutation({
    mutationFn: (files: File[]) => uploadDocuments(scopeType, scopeId, currentFolderId, files),
    onSuccess: (results) => {
      const failed = results.filter((item) => item.status === "error");
      setUploadError(
        failed.length > 0
          ? failed.map((item) => `${item.filename}: ${item.error}`).join(" · ")
          : null,
      );
      invalidate();
    },
  });

  const createFolder = useMutation({
    mutationFn: () =>
      createDocumentFolder({
        scope_type: scopeType,
        scope_id: scopeId,
        parent_folder_id: currentFolderId,
        name: newFolderName.trim(),
      }),
    onSuccess: () => {
      setNewFolderName("");
      setCreatingFolder(false);
      invalidate();
    },
  });

  const removeDocument = useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => {
      setPendingDeleteDocument(null);
      invalidate();
    },
  });

  const removeFolder = useMutation({
    mutationFn: (id: string) => deleteDocumentFolder(id),
    onSuccess: () => {
      setPendingDeleteFolder(null);
      invalidate();
    },
  });

  async function handleDownload(document: DocumentData): Promise<void> {
    const url = await getDocumentDownloadUrl(document.id);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function handleFilesSelected(event: React.ChangeEvent<HTMLInputElement>): void {
    const files = event.target.files;
    if (files && files.length > 0) {
      upload.mutate(Array.from(files));
    }
    event.target.value = "";
  }

  function toggleSort(field: DocumentSortField): void {
    if (sort === field) {
      setOrder(order === "asc" ? "desc" : "asc");
    } else {
      setSort(field);
      setOrder("asc");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Buscar por nome do arquivo…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-64 rounded border border-default bg-surface px-3 py-1.5 text-sm text-primary"
        />
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => setCreatingFolder(true)}>
          Nova pasta
        </Button>
        <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={upload.isPending}>
          {upload.isPending ? "Enviando…" : "Enviar arquivos"}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFilesSelected}
        />
      </div>

      {uploadError && <p className="text-sm text-danger">{uploadError}</p>}

      {creatingFolder && (
        <div className="flex items-center gap-2 rounded border border-default bg-surface p-2">
          <input
            autoFocus
            type="text"
            placeholder="Nome da pasta"
            value={newFolderName}
            onChange={(event) => setNewFolderName(event.target.value)}
            className="flex-1 rounded border border-default bg-surface px-2 py-1 text-sm text-primary"
          />
          <Button
            size="sm"
            disabled={newFolderName.trim() === "" || createFolder.isPending}
            onClick={() => createFolder.mutate()}
          >
            Criar
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setCreatingFolder(false);
              setNewFolderName("");
            }}
          >
            Cancelar
          </Button>
        </div>
      )}
      {createFolder.error instanceof ApiError && (
        <p className="text-sm text-danger">{createFolder.error.message}</p>
      )}

      {!isSearching && folderStack.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-sm text-muted">
          <button
            type="button"
            className="text-accent underline"
            onClick={() => setFolderStack([])}
          >
            Raiz
          </button>
          {folderStack.map((folder, index) => (
            <span key={folder.id} className="flex items-center gap-1">
              <span>/</span>
              <button
                type="button"
                className="text-accent underline"
                onClick={() => setFolderStack(folderStack.slice(0, index + 1))}
              >
                {folder.name}
              </button>
            </span>
          ))}
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted">Carregando…</p>
      ) : folders.length === 0 && documents.length === 0 ? (
        <EmptyState
          title={isSearching ? "Nada encontrado" : "Pasta vazia"}
          description={
            isSearching ? "Nenhum arquivo com esse nome." : "Envie um arquivo ou crie uma pasta."
          }
        />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-default text-left text-muted">
              <th className="cursor-pointer py-2" onClick={() => toggleSort("name")}>
                Nome {sort === "name" && (order === "asc" ? "↑" : "↓")}
              </th>
              <th className="cursor-pointer py-2" onClick={() => toggleSort("content_type")}>
                Tipo {sort === "content_type" && (order === "asc" ? "↑" : "↓")}
              </th>
              <th className="cursor-pointer py-2" onClick={() => toggleSort("size_bytes")}>
                Tamanho {sort === "size_bytes" && (order === "asc" ? "↑" : "↓")}
              </th>
              <th className="cursor-pointer py-2" onClick={() => toggleSort("created_at")}>
                Data {sort === "created_at" && (order === "asc" ? "↑" : "↓")}
              </th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {folders.map((folder) => (
              <tr key={folder.id} className="border-b border-default">
                <td className="py-2">
                  <button
                    type="button"
                    className="text-accent underline"
                    onClick={() => setFolderStack([...folderStack, folder])}
                  >
                    📁 {folder.name}
                  </button>
                </td>
                <td className="py-2 text-muted">Pasta</td>
                <td className="py-2 text-muted">—</td>
                <td className="py-2 text-muted">{formatDate(folder.created_at)}</td>
                <td className="py-2 text-right">
                  <button
                    type="button"
                    className="text-sm text-danger underline"
                    onClick={() => setPendingDeleteFolder(folder)}
                  >
                    Excluir
                  </button>
                </td>
              </tr>
            ))}
            {documents.map((document) => (
              <tr key={document.id} className="border-b border-default">
                <td className="py-2">{document.filename}</td>
                <td className="py-2 text-muted">{document.content_type}</td>
                <td className="py-2 text-muted">{formatBytes(document.size_bytes)}</td>
                <td className="py-2 text-muted">{formatDate(document.created_at)}</td>
                <td className="py-2 text-right">
                  <div className="flex justify-end gap-3">
                    <button
                      type="button"
                      className="text-sm text-accent underline"
                      onClick={() => void handleDownload(document)}
                    >
                      Baixar
                    </button>
                    <button
                      type="button"
                      className="text-sm text-danger underline"
                      onClick={() => setPendingDeleteDocument(document)}
                    >
                      Excluir
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={pendingDeleteDocument !== null}
        onOpenChange={(open) => !open && setPendingDeleteDocument(null)}
        title="Excluir documento"
        description={`Tem certeza que deseja excluir "${pendingDeleteDocument?.filename}"? Essa ação não pode ser desfeita.`}
        destructive
        onConfirm={() => {
          if (pendingDeleteDocument) removeDocument.mutate(pendingDeleteDocument.id);
        }}
      />
      <ConfirmDialog
        open={pendingDeleteFolder !== null}
        onOpenChange={(open) => !open && setPendingDeleteFolder(null)}
        title="Excluir pasta"
        description={`Tem certeza que deseja excluir "${pendingDeleteFolder?.name}"? Subpastas e arquivos dentro dela também serão excluídos.`}
        destructive
        onConfirm={() => {
          if (pendingDeleteFolder) removeFolder.mutate(pendingDeleteFolder.id);
        }}
      />
    </div>
  );
}
