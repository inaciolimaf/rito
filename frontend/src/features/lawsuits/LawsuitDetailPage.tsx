import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { Button } from "@/components/ui/button";
import { DocumentBrowser } from "@/features/documents/DocumentBrowser";
import {
  createMovement,
  getLawsuit,
  updateMovement,
  type MovementPayload,
  type TimelineItem,
} from "@/features/lawsuits/api";
import { AddMovementModal } from "@/features/lawsuits/AddMovementModal";
import { LawsuitTimeline } from "@/features/lawsuits/LawsuitTimeline";
import { TimelineFilters } from "@/features/lawsuits/TimelineFilters";
import { useTimelineKinds } from "@/features/lawsuits/useTimelineKinds";
import { formatCnj } from "@/lib/cnj";
import { listLawsuitShares, listPartnerships, shareLawsuit } from "@/features/partners/api";
import { ShareLawsuitDialog } from "@/features/partners/ShareLawsuitDialog";
import { SharedBadge } from "@/features/partners/SharedBadge";
import { GenerateBriefDialog } from "@/features/legal-agents/GenerateBriefDialog";

type Tab = "timeline" | "documents";

const TABS: { value: Tab; label: string }[] = [
  { value: "timeline", label: "Linha do tempo" },
  { value: "documents", label: "Documentos" },
];

/** Detalhe do processo (spec 026 §6) — a timeline é a aba principal; a nuvem de
 * documentos (spec 063) é a 2ª aba. */
export function LawsuitDetailPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "documents" ? "documents" : "timeline";
  const queryClient = useQueryClient();
  const { kinds, setKinds, isLoading: kindsLoading } = useTimelineKinds();
  const [modalOpen, setModalOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<TimelineItem | null>(null);
  const [shareOpen, setShareOpen] = React.useState(false);
  const [briefOpen, setBriefOpen] = React.useState(false);

  const { data: lawsuit, isLoading } = useQuery({
    queryKey: ["lawsuits", id],
    queryFn: () => getLawsuit(id!),
    enabled: !!id,
  });

  // Spec 079: o badge de compartilhamento (regra 12) é permanente enquanto houver
  // parceiro com acesso — por isso a consulta vive no detalhe, não no diálogo.
  const { data: shares } = useQuery({
    queryKey: ["lawsuits", id, "shares"],
    queryFn: () => listLawsuitShares(id!),
    enabled: !!id,
  });
  const { data: partnerships } = useQuery({
    queryKey: ["partnerships", "ATIVA"],
    queryFn: () => listPartnerships("ATIVA"),
  });
  const activeShares = shares?.items ?? [];

  async function handleSubmitMovement(values: MovementPayload): Promise<void> {
    if (!id) return;
    if (editing) {
      await updateMovement(id, editing.id, values);
    } else {
      await createMovement(id, values);
    }
    await queryClient.invalidateQueries({ queryKey: ["lawsuit-timeline", id] });
  }

  if (isLoading || !lawsuit) {
    return <p className="p-6 text-sm text-muted">Carregando processo…</p>;
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-muted">
            <Link to="/lawsuits" className="underline">
              Processos
            </Link>{" "}
            / {lawsuit.action_group_name}
          </p>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-primary">
            {lawsuit.process_number
              ? formatCnj(lawsuit.process_number)
              : lawsuit.folder || "Processo sem número"}
            {activeShares[0] && (
              <SharedBadge partnerName={activeShares[0].partner_name} count={activeShares.length} />
            )}
          </h1>
          <p className="text-sm text-muted">
            {lawsuit.action_group_name} · {lawsuit.step_name}
            {lawsuit.is_archived ? " · Arquivado" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setShareOpen(true)}>
            Compartilhar
          </Button>
          {/* Spec 087: gerar minuta a partir DESTE processo — o agente coleta o
              contexto sozinho, por consulta ao sistema. */}
          <Button variant="ghost" onClick={() => setBriefOpen(true)}>
            Gerar minuta com IA
          </Button>
          {tab === "timeline" && (
            <Button
              onClick={() => {
                setEditing(null);
                setModalOpen(true);
              }}
            >
              Nova movimentação
            </Button>
          )}
        </div>
      </div>

      {id && (
        <GenerateBriefDialog
          open={briefOpen}
          onOpenChange={setBriefOpen}
          lawsuitId={id}
          onOpenTemplate={(templateId) => {
            setBriefOpen(false);
            navigate(`/library/${templateId}`);
          }}
        />
      )}

      <ShareLawsuitDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        partnerships={partnerships?.items ?? []}
        lawsuitLabel={
          lawsuit.process_number
            ? formatCnj(lawsuit.process_number)
            : lawsuit.folder || "Processo sem número"
        }
        onShare={async (payload) => {
          const created = await shareLawsuit(id!, payload);
          await queryClient.invalidateQueries({ queryKey: ["lawsuits", id, "shares"] });
          return created;
        }}
      />

      <TabBar
        items={TABS}
        active={tab}
        ariaLabel="Seções do processo"
        onSelect={(value) => setSearchParams(value === "timeline" ? {} : { tab: value })}
      />

      {tab === "documents" && id && <DocumentBrowser scopeType="LAWSUIT" scopeId={id} />}

      {tab === "timeline" && (
        <>
          {!kindsLoading && <TimelineFilters kinds={kinds} onChange={setKinds} />}

          {id && (
            <LawsuitTimeline
              lawsuitId={id}
              kinds={kinds}
              onEditMovement={(item) => {
                setEditing(item);
                setModalOpen(true);
              }}
            />
          )}
        </>
      )}

      <AddMovementModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        editing={editing}
        onSubmit={handleSubmitMovement}
      />
    </div>
  );
}
