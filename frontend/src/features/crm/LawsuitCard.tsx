import { StagnantBadge } from "@/components/domain/StagnantBadge";
import type { BoardCard } from "@/features/crm/api";
import { formatBrl } from "@/lib/money";

function daysInStage(stageEnteredAt: string): number {
  const entered = new Date(stageEnteredAt).getTime();
  const diffMs = Date.now() - entered;
  return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
}

export function partiesSummary(card: BoardCard): string {
  const names = card.parties.slice(0, 2).map((party) => party.name);
  const extra = card.parties_total - names.length;
  return extra > 0 ? `${names.join(", ")} +${extra}` : names.join(", ") || "Sem partes";
}

/** Card do processo no Kanban (spec 051, regra 2): partes (2 + contador), tipo de
 * ação, valor da causa, responsável, tempo na etapa. */
export function LawsuitCard({ card }: { card: BoardCard }): JSX.Element {
  const days = daysInStage(card.stage_entered_at);
  return (
    <div className="space-y-1 text-sm">
      {card.is_stagnant && <StagnantBadge daysInStage={days} stagnantDays={card.stagnant_days} />}
      <p className="font-medium text-primary">{partiesSummary(card)}</p>
      <p className="text-xs text-muted">{card.lawsuit_type_name}</p>
      {card.process_number && <p className="text-xs text-muted">{card.process_number}</p>}
      <p className="text-xs text-muted">{formatBrl(card.case_value)}</p>
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{card.responsible_name}</span>
        <span>{days === 0 ? "hoje" : `${days} dia${days === 1 ? "" : "s"}`}</span>
      </div>
    </div>
  );
}
