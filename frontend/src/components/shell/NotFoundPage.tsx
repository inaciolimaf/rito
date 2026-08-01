import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";

export function NotFoundPage(): JSX.Element {
  const navigate = useNavigate();

  return (
    <EmptyState
      title="Página não encontrada."
      description="A rota que você tentou acessar não existe."
      action={{ label: "Voltar para o início", onClick: () => navigate("/home") }}
    />
  );
}
