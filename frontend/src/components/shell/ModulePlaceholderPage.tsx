import { EmptyState } from "@/components/domain/EmptyState";

export interface ModulePlaceholderPageProps {
  title: string;
}

export function ModulePlaceholderPage({ title }: ModulePlaceholderPageProps): JSX.Element {
  return (
    <EmptyState
      title={title}
      description="Este módulo ainda não foi implementado — a topologia de navegação já está pronta."
    />
  );
}
