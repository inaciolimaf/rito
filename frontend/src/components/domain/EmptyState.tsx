import * as React from "react";

import { Button } from "@/components/ui/button";

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  role?: "alert" | "status";
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  role = "status",
}: EmptyStateProps): JSX.Element {
  return (
    <div
      role={role}
      className="flex flex-col items-center gap-2 rounded border border-default bg-surface p-10 text-center"
    >
      {icon}
      <p className="font-medium text-primary">{title}</p>
      {description && <p className="text-sm text-muted">{description}</p>}
      {action && (
        <Button type="button" size="sm" className="mt-2" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
