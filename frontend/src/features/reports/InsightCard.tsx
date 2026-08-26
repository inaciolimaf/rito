import { AlertTriangle, Info, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { InsightData } from "@/features/reports/insights";

const SEVERITY = {
  critical: { icon: AlertTriangle, className: "border-danger bg-danger/10 text-danger" },
  warning: { icon: TriangleAlert, className: "border-warning bg-warning/10 text-warning" },
  info: { icon: Info, className: "border-default bg-surface text-muted" },
} as const;

function subjectLink(insight: InsightData): string | null {
  if (!insight.subject_id) return null;
  if (insight.subject_type === "lawsuit") return `/lawsuits/${insight.subject_id}`;
  if (insight.subject_type === "customer") return `/customers`;
  return null;
}

export interface InsightCardProps {
  insight: InsightData;
  onDismiss: (id: string) => void;
}

/** Um aviso do painel de insights (spec 089, regras 8 e 12).
 *
 * Todo insight leva ao registro que o originou — alerta genérico é ruído que ninguém
 * sabe o que fazer com, e vira barulho que as pessoas aprendem a ignorar. */
export function InsightCard({ insight, onDismiss }: InsightCardProps): JSX.Element {
  const severity = SEVERITY[insight.severity] ?? SEVERITY.info;
  const Icon = severity.icon;
  const href = subjectLink(insight);
  return (
    <article
      data-testid={`insight-${insight.kind}`}
      data-severity={insight.severity}
      className={`space-y-2 rounded border p-3 ${severity.className}`}
    >
      <p className="flex items-center gap-2 font-medium">
        <Icon aria-hidden className="size-4" />
        {insight.title}
      </p>
      <p className="text-sm text-primary">{insight.body}</p>
      <div className="flex items-center justify-between">
        {href ? (
          <Link to={href} className="text-xs underline">
            Abrir o registro
          </Link>
        ) : (
          <span />
        )}
        <Button type="button" size="sm" variant="ghost" onClick={() => onDismiss(insight.id)}>
          Dispensar
        </Button>
      </div>
    </article>
  );
}
