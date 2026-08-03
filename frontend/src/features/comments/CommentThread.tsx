import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { AttachmentList } from "@/features/attachments/AttachmentList";
import { FileDropzone } from "@/features/attachments/FileDropzone";
import { uploadAttachment } from "@/features/attachments/api";
import {
  createComment,
  deleteComment,
  listComments,
  searchMentionableUsers,
  updateComment,
  type CommentData,
} from "@/features/comments/api";
import { CommentEditor } from "@/features/comments/CommentEditor";
import { useAuth } from "@/providers/AuthProvider";

export interface CommentThreadProps {
  postId: string;
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  // DD/MM/AAAA (CLAUDE.md §9) com hora — comentário precisa de horário.
  return `${date.toLocaleDateString("pt-BR")} ${date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

function CommentItem({
  comment,
  currentUserId,
  postId,
}: {
  comment: CommentData;
  currentUserId: string | undefined;
  postId: string;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [editing, setEditing] = React.useState(false);

  async function invalidate(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["comments", postId] });
  }

  if (comment.deleted) {
    // Regra 4: o comentário removido continua na thread, mascarado.
    return (
      <li className="rounded border border-default bg-surface-muted p-3 text-sm italic text-muted">
        comentário removido
      </li>
    );
  }

  const isAuthor = comment.author.id === currentUserId;

  return (
    <li className="space-y-1 rounded border border-default bg-surface p-3">
      <div className="flex items-center justify-between text-xs text-muted">
        <span className="font-medium text-primary">{comment.author.name}</span>
        <span>
          {formatDateTime(comment.created_at)}
          {comment.updated_at !== comment.created_at ? " · editado" : ""}
        </span>
      </div>
      {editing ? (
        <CommentEditor
          initialValue={comment.body ?? ""}
          submitLabel="Salvar"
          onSearchMentions={searchMentionableUsers}
          onSubmit={async (body) => {
            await updateComment(comment.id, body);
            setEditing(false);
            await invalidate();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <p className="whitespace-pre-wrap text-sm text-primary">{comment.body}</p>
      )}
      <AttachmentList attachments={comment.attachments} onRemoved={() => void invalidate()} />
      {!editing && (
        <div className="flex gap-3">
          <FileDropzone
            onFiles={(files) => {
              void Promise.all(
                files.map((file) => uploadAttachment("comment", comment.id, file)),
              ).then(invalidate);
            }}
          />
          {isAuthor && (
            <>
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="text-xs text-accent underline"
              >
                Editar
              </button>
              <button
                type="button"
                onClick={() => void deleteComment(comment.id).then(invalidate)}
                className="text-xs text-danger underline"
              >
                Excluir
              </button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

/** Thread de comentários da tarefa (spec 035 §6): ordem crescente (regra 10), removido
 * aparece mascarado (regra 4), editor com `@menções` ao final. */
export function CommentThread({ postId }: CommentThreadProps): JSX.Element {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["comments", postId],
    queryFn: () => listComments(postId),
  });

  async function invalidate(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["comments", postId] });
  }

  const items = data?.items ?? [];

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-primary">
        Comentários{data ? ` (${data.total})` : ""}
      </h2>
      <ul className="space-y-2">
        {items.map((comment) => (
          <CommentItem
            key={comment.id}
            comment={comment}
            currentUserId={user?.id}
            postId={postId}
          />
        ))}
      </ul>
      {items.length === 0 && data && (
        <p className="text-sm text-muted">Nenhum comentário ainda — comece a conversa.</p>
      )}
      <CommentEditor
        onSearchMentions={searchMentionableUsers}
        onSubmit={async (body) => {
          await createComment(postId, body);
          await invalidate();
        }}
      />
    </section>
  );
}
