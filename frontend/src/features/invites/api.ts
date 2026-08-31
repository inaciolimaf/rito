import { apiRequest } from "@/lib/api";

export interface AcceptInvitePayload {
  token: string;
  name: string;
  password: string;
  /** O convite chega por e-mail para quem ainda não tem sessão: o tenant vem no link,
   * porque `POST /invitations/accept` é pré-autenticação e exige `X-Tenant-Id` (o RLS
   * não acha a linha certa sem saber o tenant antes da query — regra da spec 004). */
  tenantId: string;
}

export async function acceptInvite({
  token,
  name,
  password,
  tenantId,
}: AcceptInvitePayload): Promise<void> {
  await apiRequest<void>("/api/v1/invitations/accept", {
    method: "POST",
    body: { token, name, password },
    headers: { "X-Tenant-Id": tenantId },
  });
}
