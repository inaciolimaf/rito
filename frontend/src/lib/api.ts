import { ApiError, toApiError } from "@/lib/errors";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const REFRESH_TOKEN_KEY = "rito.refresh_token";

/** Disparado quando o refresh falha e a sessão precisa ser encerrada (regra 2). */
export const SESSION_EXPIRED_EVENT = "rito:session-expired";

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

// Token de acesso só em memória; refresh em localStorage (regra 5). Recarregar a página
// derruba o access token, mas o AuthProvider usa o refresh token para reautenticar em silêncio.
let accessToken: string | null = null;

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setSession(tokens: TokenPair | null): void {
  if (tokens) {
    accessToken = tokens.accessToken;
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
  } else {
    accessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
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

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }

  const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    setSession(null);
    return null;
  }

  const body = (await response.json()) as RefreshResponseBody;
  setSession({ accessToken: body.access_token, refreshToken: body.refresh_token });
  return body.access_token;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  _isRetry = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  const wasAuthenticated = headers.has("Authorization");

  const response = await fetch(`${BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  // Só tenta refresh se a requisição tinha Bearer token — um 401 de /auth/login (sem
  // token nenhum) é credencial errada, não sessão expirada, e nunca deve virar refresh.
  if (response.status === 401 && !_isRetry && wasAuthenticated) {
    if (!pendingRefresh) {
      pendingRefresh = refreshAccessToken().finally(() => {
        pendingRefresh = null;
      });
    }
    const newAccessToken = await pendingRefresh;

    if (newAccessToken) {
      return apiRequest<T>(path, options, true);
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

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
