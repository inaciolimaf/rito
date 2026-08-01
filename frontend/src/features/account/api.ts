import { apiRequest } from "@/lib/api";
import { ApiError } from "@/lib/errors";

export interface AccountData {
  id: string;
  name: string;
  alternate_name: string;
  identification: string;
  country: string;
  state: string;
  city: string;
  postal_code: string;
  street: string;
  region: string;
  cellphone: string;
  phone: string;
  email: string;
  email_admin: string;
  site: string | null;
  timezone: string;
  logo_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountFormValues {
  name: string;
  alternate_name: string;
  identification: string;
  country: string;
  state: string;
  city: string;
  postal_code: string;
  street: string;
  region: string;
  cellphone: string;
  phone: string;
  email: string;
  email_admin: string;
  site: string;
  timezone: string;
}

/** GET devolve 404 antes do primeiro PUT (regra: PUT cria-ou-atualiza, spec 011,
 * Descobertas) — tratado aqui como "ainda sem conta", não como erro. */
export async function getAccount(): Promise<AccountData | null> {
  try {
    return await apiRequest<AccountData>("/api/v1/account");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function updateAccount(values: AccountFormValues): Promise<AccountData> {
  return apiRequest<AccountData>("/api/v1/account", { method: "PUT", body: values });
}

export async function uploadAccountLogo(file: File): Promise<AccountData> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<AccountData>("/api/v1/account/logo", { method: "POST", body: formData });
}
