import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { acceptInvite } from "@/features/invites/api";
import { ApiError } from "@/lib/errors";

/** Spec 102, Bloco C — fecha a dívida nº 9.
 *
 * O convite de usuário existe desde a spec 012, mas não havia tela para aceitá-lo: o
 * token era criado e não tinha para onde ir. `token` e `tenant` vêm do link do e-mail.
 */
export function AcceptInvitePage(): JSX.Element {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const tenantId = params.get("tenant") ?? "";

  const [name, setName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const linkIncompleto = !token || !tenantId;

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await acceptInvite({ token, name, password, tenantId });
      // A sessão não é criada aqui: quem aceita acabou de definir a senha e entra por
      // ela, pelo caminho normal. Evita um segundo jeito de virar sessão autenticada.
      navigate("/login", { replace: true });
    } catch (submitError) {
      setError(
        submitError instanceof ApiError
          ? submitError.message
          : "Não foi possível aceitar o convite.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-primary">Aceitar convite</h1>
        <p className="text-sm text-secondary">
          Escolha seu nome e uma senha para entrar no escritório.
        </p>
      </div>

      {linkIncompleto ? (
        <div className="space-y-3">
          <p role="alert" className="text-sm text-danger">
            Link de convite incompleto. Abra o link exatamente como ele veio no e-mail.
          </p>
          <Link to="/login" className="text-sm text-accent underline">
            Ir para o login
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="invite-name">Nome</Label>
            <Input
              id="invite-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="invite-password">Senha</Label>
            <Input
              id="invite-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Enviando…" : "Criar acesso"}
          </Button>
        </form>
      )}
    </main>
  );
}
