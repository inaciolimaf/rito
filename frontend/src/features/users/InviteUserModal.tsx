import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormModal } from "@/components/domain/FormModal";
import type { Occupation } from "@/features/users/api";
import {
  DEFAULT_INVITE_VALUES,
  inviteUserSchema,
  type InviteUserFormValues,
} from "@/features/users/schema";
import { ApiError } from "@/lib/errors";

export interface InviteUserModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  occupations: Occupation[];
  serverError?: ApiError | null;
  onSubmit: (values: InviteUserFormValues) => Promise<void>;
}

export function InviteUserModal({
  open,
  onOpenChange,
  occupations,
  serverError,
  onSubmit,
}: InviteUserModalProps): JSX.Element {
  return (
    <FormModal
      open={open}
      onOpenChange={onOpenChange}
      title="Convidar usuário"
      description="Um e-mail com o link de ativação será enviado. O convite expira em 7 dias."
      schema={inviteUserSchema}
      defaultValues={DEFAULT_INVITE_VALUES}
      serverError={serverError}
      submitLabel="Enviar convite"
      onSubmit={onSubmit}
    >
      {(form) => (
        <>
          <div className="space-y-1">
            <Label htmlFor="invite-email">E-mail</Label>
            <Input id="invite-email" type="email" {...form.register("email")} />
            {form.formState.errors.email && (
              <p className="text-sm text-danger">{form.formState.errors.email.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <Label htmlFor="invite-occupation">Cargo</Label>
            <select
              id="invite-occupation"
              className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              {...form.register("occupation_id")}
            >
              <option value="">Selecione...</option>
              {occupations.map((occupation) => (
                <option key={occupation.id} value={occupation.id}>
                  {occupation.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="invite-role">Perfil</Label>
            <select
              id="invite-role"
              className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              {...form.register("role")}
            >
              <option value="COLABORADOR">Colaborador</option>
              <option value="ADMINISTRADOR">Administrador</option>
              <option value="GESTOR">Gestor</option>
            </select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="invite-financial">Acesso financeiro</Label>
            <select
              id="invite-financial"
              className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              {...form.register("financial_access")}
            >
              <option value="NONE">Sem acesso</option>
              <option value="READ_ONLY">Somente visualização</option>
              <option value="FULL">Acesso completo</option>
            </select>
          </div>
        </>
      )}
    </FormModal>
  );
}
