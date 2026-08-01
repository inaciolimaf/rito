import * as React from "react";

import {
  SESSION_EXPIRED_EVENT,
  apiRequest,
  getRefreshToken,
  getStoredTenantId,
  setSession,
} from "@/lib/api";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  tenant: string;
  role: string;
  financialAccess: string;
  capabilities: string[];
}

interface MeResponseBody {
  id: string;
  name: string;
  email: string;
  tenant: string;
  role: string;
  financial_access: string;
  capabilities: string[];
}

interface LoginResponseBody {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface LoginParams {
  tenantId: string;
  email: string;
  password: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (params: LoginParams) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

function toAuthUser(body: MeResponseBody): AuthUser {
  return {
    id: body.id,
    name: body.name,
    email: body.email,
    tenant: body.tenant,
    role: body.role,
    financialAccess: body.financial_access,
    capabilities: body.capabilities,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  const loadCurrentUser = React.useCallback(async (): Promise<void> => {
    try {
      const me = await apiRequest<MeResponseBody>("/api/v1/auth/me");
      setUser(toAuthUser(me));
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (!getRefreshToken()) {
      setIsLoading(false);
      return;
    }
    void loadCurrentUser();
  }, [loadCurrentUser]);

  React.useEffect(() => {
    const handleSessionExpired = (): void => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const login = React.useCallback(
    async ({ tenantId, email, password }: LoginParams): Promise<void> => {
      const response = await apiRequest<LoginResponseBody>("/api/v1/auth/login", {
        method: "POST",
        headers: { "X-Tenant-Id": tenantId },
        body: { email, password },
      });
      setSession({
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        tenantId,
      });
      await loadCurrentUser();
    },
    [loadCurrentUser],
  );

  const logout = React.useCallback(async (): Promise<void> => {
    const refreshToken = getRefreshToken();
    const tenantId = getStoredTenantId();
    if (refreshToken && tenantId) {
      await apiRequest("/api/v1/auth/logout", {
        method: "POST",
        headers: { "X-Tenant-Id": tenantId },
        body: { refresh_token: refreshToken },
      }).catch(() => undefined);
    }
    setSession(null);
    setUser(null);
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({ user, isLoading, isAuthenticated: user !== null, login, logout }),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth precisa estar dentro de um AuthProvider.");
  }
  return context;
}
