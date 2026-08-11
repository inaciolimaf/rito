import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { AttachmentList } from "@/features/attachments/AttachmentList";
import { FileDropzone } from "@/features/attachments/FileDropzone";
import { uploadAttachment, type AttachmentData } from "@/features/attachments/api";
import { CommentThread } from "@/features/comments/CommentThread";
import { getPost } from "@/features/posts/api";
import { PriorityBadge } from "@/features/posts/PriorityBadge";
import { PUBLICATIONS_TASK_TYPE_NAME } from "@/features/publications/api";
import { apiRequest } from "@/lib/api";

function formatDate(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

/** Detalhe da tarefa (spec 035 §6): os dados do post, os anexos da tarefa e a thread
 * de comentários — o destino do link da notificação de menção (`/posts/{id}`). */
export function PostDetailPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data: post, isLoading } = useQuery({
    queryKey: ["posts", id],
    queryFn: () => getPost(id!),
    enabled: !!id,
  });
  const { data: attachments } = useQuery({
    queryKey: ["post-attachments", id],
    queryFn: () =>
      apiRequest<AttachmentData[]>(
        `/api/v1/attachments?attached_to_type=post&attached_to_id=${id}`,
      ),
    enabled: !!id,
  });

  if (isLoading || !post) {
    return <p className="p-6 text-sm text-muted">Carregando tarefa…</p>;
  }

  async function invalidateAttachments(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["post-attachments", id] });
  }

  // Dívida técnica #18 (spec 050): a tarefa de intimação (spec 045) nunca calcula prazo
  // de verdade (fica pra 086) — sem isso, "sem prazo" e "prazo não calculado" ficariam
  // visualmente idênticos (nada aparece). Distinguir evita o usuário achar que é só um
  // campo vazio que ele pode preencher à toa.
  const isPublicationTask = post.task_type_name === PUBLICATIONS_TASK_TYPE_NAME;
  const deadlineLabel = post.deadline_date
    ? `Prazo fatal: ${formatDate(post.deadline_date)}`
    : isPublicationTask
      ? "Prazo não calculado"
      : null;

  return (
    <div className="space-y-6 p-6">
      <div>
        <p className="text-xs text-muted">
          <Link to={`/lawsuits/${post.lawsuit_id}`} className="underline">
            Processo
          </Link>{" "}
          / Tarefa
        </p>
        <h1 className="flex items-center gap-2 text-lg font-semibold text-primary">
          {post.task_type_name}
          <PriorityBadge
            isImportant={post.is_important}
            isUrgent={post.is_urgent}
            isPrivate={post.is_private}
          />
        </h1>
        <p className="text-sm text-muted">
          {formatDate(post.scheduled_date)}
          {post.scheduled_time ? ` às ${post.scheduled_time.slice(0, 5)}` : ""}
          {deadlineLabel ? ` · ${deadlineLabel}` : ""}
          {post.location ? ` · ${post.location}` : ""}
        </p>
        <p className="text-sm text-muted">
          Responsáveis: {post.assignees.map((assignee) => assignee.name).join(", ")}
        </p>
        {post.comments && <p className="mt-2 whitespace-pre-wrap text-sm">{post.comments}</p>}
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-primary">Anexos</h2>
        <AttachmentList
          attachments={attachments ?? []}
          onRemoved={() => void invalidateAttachments()}
        />
        <FileDropzone
          onFiles={(files) => {
            void Promise.all(files.map((file) => uploadAttachment("post", id!, file))).then(
              invalidateAttachments,
            );
          }}
        />
      </section>

      <CommentThread postId={post.id} />
    </div>
  );
}
