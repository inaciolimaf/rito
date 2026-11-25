import * as React from "react";
import { useLocation } from "react-router-dom";

interface Props {
  children: React.ReactNode;
  /** Quando muda, o erro some: navegar para outra rota tira o usuário da tela quebrada. */
  resetKey?: string;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<Props, State> {
  override state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  override componentDidCatch(error: unknown): void {
    console.error("Erro não tratado na aplicação:", error);
  }

  override componentDidUpdate(previous: Props): void {
    if (this.state.hasError && previous.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  override render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-surface text-primary">
          <p>Algo deu errado. Recarregue a página.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * Erro de uma tela não derruba o roteador inteiro: esta fronteira fica dentro do
 * BrowserRouter e se rearma a cada navegação (frontend-standard, defaultErrorComponent).
 */
export function RouteErrorBoundary({ children }: { children: React.ReactNode }): JSX.Element {
  const { pathname } = useLocation();
  return <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>;
}
