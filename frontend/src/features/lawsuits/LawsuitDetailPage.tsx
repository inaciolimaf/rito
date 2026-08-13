import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

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

type Tab = "timeline" | "documents";

const TABS: { value: Tab; label: string }[] = [
  { value: "timeline", label: "Linha do tempo" },
  { value: "documents", label: "Documentos" },
];

/** Detalhe do processo (spec 026 §6) — a timeline é a aba principal; a nuvem de
 * documentos (spec 063) é a 2ª aba. */
export function LawsuitDetailPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "documents" ? "documents" : "timeline";
  const queryClient = useQueryClient();
  const { kinds, setKinds, isLoading: kindsLoading } = useTimelineKinds();
  const [modalOpen, setModalOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<TimelineItem | null>(null);

  const { data: lawsuit, isLoading } = useQuery({
    queryKey: ["lawsuits", id],
    queryFn: () => getLawsuit(id!),
    enabled: !!id,
  });

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
          <h1 className="text-lg font-semibold text-primary">
            {lawsuit.process_number
              ? formatCnj(lawsuit.process_number)
              : lawsuit.folder || "Processo sem número"}
          </h1>
          <p className="text-sm text-muted">
            {lawsuit.action_group_name} · {lawsuit.step_name}
            {lawsuit.is_archived ? " · Arquivado" : ""}
          </p>
        </div>
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
