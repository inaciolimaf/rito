import { ApiError, toApiError } from "@/lib/errors";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const REFRESH_TOKEN_KEY = "rito.refresh_token";
const TENANT_ID_KEY = "rito.tenant_id";

/** Disparado quando o refresh falha e a sessão precisa ser encerrada (regra 2). */
export const SESSION_EXPIRED_EVENT = "rito:session-expired";

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  tenantId: string;
}

// Token de acesso só em memória; refresh em localStorage (regra 5). Recarregar a página
// derruba o access token, mas o AuthProvider usa o refresh token para reautenticar em silêncio.
let accessToken: string | null = null;

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

// O backend exige X-Tenant-Id em /auth/refresh e /auth/logout (spec 004: pré-autenticação
// sempre resolve o tenant pelo header, nunca pelo corpo) — sem persistir isso ao lado do
// refresh token, o refresh em silêncio ao carregar a página falha com 400.
/** Token de acesso corrente, para quem precisa montar a requisição na mão — hoje só o
 * streaming SSE do editor (spec 088), que é POST e não passa pelo `apiRequest`. */
export function getAccessToken(): string | null {
  return accessToken;
}

export function getStoredTenantId(): string | null {
  return localStorage.getItem(TENANT_ID_KEY);
}

export function setSession(tokens: TokenPair | null): void {
  if (tokens) {
    accessToken = tokens.accessToken;
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
    localStorage.setItem(TENANT_ID_KEY, tokens.tenantId);
  } else {
    accessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(TENANT_ID_KEY);
  }
}

interface RefreshResponseBody {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

// Compartilhada entre chamadas concorrentes: só a primeira 401 dispara o refresh de verdade,
// as demais esperam nesta mesma promise e reexecutam depois (regra 1).
let pendingRefresh: Promise<string | null> | null = null;

// Endpoints pré-autenticação: um 401 aqui é sempre um erro de credencial/token em si, nunca
// "sessão expirada" — tentar refresh nesses casos é sem sentido (ou recursivo, no caso do
// próprio /refresh). Todo o resto — incluindo /auth/me SEM access token, o caso normal de
// reautenticação silenciosa ao carregar a página — deve tentar refresh.
const NO_REFRESH_PATHS = [
  "/api/v1/auth/login",
  "/api/v1/auth/refresh",
  "/api/v1/auth/forgot-password",
  "/api/v1/auth/reset-password",
];

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  const tenantId = getStoredTenantId();
  if (!refreshToken || !tenantId) {
    return null;
  }

  const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Tenant-Id": tenantId },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    setSession(null);
    return null;
  }

  const body = (await response.json()) as RefreshResponseBody;
  setSession({ accessToken: body.access_token, refreshToken: body.refresh_token, tenantId });
  return body.access_token;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

async function fetchWithAuth(
  path: string,
  options: RequestOptions,
  _isRetry: boolean,
): Promise<Response> {
  const isFormData = options.body instanceof FormData;
  const headers = new Headers(options.headers);
  // FormData (upload de arquivo, spec 011): o browser define o Content-Type sozinho, com
  // o boundary do multipart — setar "application/json" aqui quebraria o parse no servidor.
  if (!isFormData) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const body = isFormData
    ? (options.body as FormData)
    : options.body !== undefined
      ? JSON.stringify(options.body)
      : undefined;

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
  });

  if (response.status === 401 && !_isRetry && !NO_REFRESH_PATHS.includes(path)) {
    if (!pendingRefresh) {
      pendingRefresh = refreshAccessToken().finally(() => {
        pendingRefresh = null;
      });
    }
    const newAccessToken = await pendingRefresh;

    if (newAccessToken) {
      return fetchWithAuth(path, options, true);
    }

    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    throw new ApiError({
      type: "about:blank",
      title: "Sessão expirada",
      status: 401,
      detail: "Sua sessão expirou. Faça login novamente.",
      instance: path,
    });
  }

  if (!response.ok) {
    throw await toApiError(response, path);
  }

  return response;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetchWithAuth(path, options, false);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Para respostas binárias (export xlsx/pdf, spec 019) — mesma autenticação/retry de
 * `apiRequest`, só troca o parse final de JSON por Blob. */
export async function apiRequestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const response = await fetchWithAuth(path, options, false);
  return response.blob();
}
