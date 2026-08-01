import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

// Não existe (ainda) endpoint público que resolva um slug de escritório para o tenant_id
// (UUID) — o backend exige X-Tenant-Id como UUID desde a spec 004. Até a 011 (Escritório)
// trazer essa resolução, o próprio usuário informa o ID aqui.
const loginSchema = z.object({
  tenantId: z.string().uuid("Informe o ID do escritório (UUID)."),
  email: z.string().email("E-mail inválido."),
  password: z.string().min(1, "Informe a senha."),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginPage(): JSX.Element {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [formError, setFormError] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values: LoginFormValues): Promise<void> => {
    setFormError(null);
    try {
      await login(values);
      const next = searchParams.get("next") ?? "/";
      navigate(next, { replace: true });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Não foi possível entrar.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <form
        onSubmit={(event) => void handleSubmit(onSubmit)(event)}
        noValidate
        className="w-full max-w-sm space-y-4 rounded border border-default bg-surface p-6"
      >
        <h1 className="text-lg font-semibold text-primary">Entrar no Rito</h1>

        <div className="space-y-1">
          <Label htmlFor="tenantId">ID do escritório</Label>
          <Input id="tenantId" autoComplete="off" {...register("tenantId")} />
          {errors.tenantId && <p className="text-sm text-danger">{errors.tenantId.message}</p>}
        </div>

        <div className="space-y-1">
          <Label htmlFor="email">E-mail</Label>
          <Input id="email" type="email" autoComplete="username" {...register("email")} />
          {errors.email && <p className="text-sm text-danger">{errors.email.message}</p>}
        </div>

        <div className="space-y-1">
          <Label htmlFor="password">Senha</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            {...register("password")}
          />
          {errors.password && <p className="text-sm text-danger">{errors.password.message}</p>}
        </div>

        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Entrando..." : "Entrar"}
        </Button>
      </form>
    </div>
  );
}
