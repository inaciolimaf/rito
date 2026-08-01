import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

export interface StatCardProps {
  label: string;
  value: string | number;
  previousValue?: number;
  isLoading?: boolean;
  href?: string;
}

function computeTrend(
  value: string | number,
  previousValue?: number,
): "up" | "down" | "flat" | null {
  if (previousValue === undefined || typeof value !== "number") return null;
  if (value > previousValue) return "up";
  if (value < previousValue) return "down";
  return "flat";
}

function computeVariationLabel(value: string | number, previousValue?: number): string | null {
  if (previousValue === undefined || typeof value !== "number") return null;
  if (previousValue === 0) return value === 0 ? "0%" : "+100%";
  const variation = ((value - previousValue) / previousValue) * 100;
  const sign = variation > 0 ? "+" : "";
  return `${sign}${variation.toFixed(0)}%`;
}

const TREND_ICON = {
  up: TrendingUp,
  down: TrendingDown,
  flat: Minus,
};

export function StatCard({
  label,
  value,
  previousValue,
  isLoading = false,
  href,
}: StatCardProps): JSX.Element {
  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 rounded border border-default bg-surface p-4">
        <div className="h-4 w-24 animate-pulse rounded bg-surface-muted" />
        <div className="h-8 w-16 animate-pulse rounded bg-surface-muted" />
      </div>
    );
  }

  const trend = computeTrend(value, previousValue);
  const variationLabel = computeVariationLabel(value, previousValue);
  const TrendIcon = trend ? TREND_ICON[trend] : null;

  const content = (
    <div className="flex flex-col gap-1 rounded border border-default bg-surface p-4">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-2xl font-semibold text-primary">{value}</span>
      {variationLabel && TrendIcon && (
        <span
          className={
            trend === "up"
              ? "flex items-center gap-1 text-sm text-success"
              : trend === "down"
                ? "flex items-center gap-1 text-sm text-danger"
                : "flex items-center gap-1 text-sm text-muted"
          }
        >
          <TrendIcon className="h-3 w-3" />
          {variationLabel} vs. período anterior
        </span>
      )}
    </div>
  );

  if (href) {
    return (
      <Link
        to={href}
        className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
      >
        {content}
      </Link>
    );
  }

  return content;
}
