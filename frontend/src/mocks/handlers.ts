import { http, HttpResponse } from "msw";

export const BASE_URL = "http://localhost:8000";

export const validCredentials = {
  tenantId: "11111111-1111-1111-1111-111111111111",
  email: "user@example.com",
  password: "SenhaForte123!",
};

export const validUser = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "Usuário de Teste",
  email: validCredentials.email,
  tenant: validCredentials.tenantId,
  role: "COLABORADOR",
  financial_access: "NONE",
  capabilities: ["tasks.view"],
};

const VALID_ACCESS_TOKENS = new Set(["access-token-1", "access-token-2"]);
const VALID_REFRESH_TOKENS = new Set(["refresh-token-1", "refresh-token-2"]);

let refreshCallCount = 0;

export function resetMswState(): void {
  refreshCallCount = 0;
  VALID_ACCESS_TOKENS.clear();
  VALID_ACCESS_TOKENS.add("access-token-1");
  VALID_ACCESS_TOKENS.add("access-token-2");
  VALID_REFRESH_TOKENS.clear();
  VALID_REFRESH_TOKENS.add("refresh-token-1");
  VALID_REFRESH_TOKENS.add("refresh-token-2");
}

export function getRefreshCallCount(): number {
  return refreshCallCount;
}

function unauthorized(instance: string, detail: string) {
  return HttpResponse.json(
    {
      type: "https://rito.app/errors/unauthorized",
      title: "Não autenticado",
      status: 401,
      detail,
      instance,
    },
    { status: 401 },
  );
}

// O backend (spec 004) exige X-Tenant-Id em TODO endpoint pré-autenticação, incluindo
// /refresh e /logout — não só /login. Reproduzido aqui porque um mock que não valida isso
// deixa passar um bug real (visto na spec 008: o frontend não mandava o header no refresh).
function missingTenantId(instance: string) {
  return HttpResponse.json(
    {
      type: "https://rito.app/errors/bad-request",
      title: "Requisição inválida",
      status: 400,
      detail: "Cabeçalho X-Tenant-Id é obrigatório.",
      instance,
    },
    { status: 400 },
  );
}

// spec 011, regra 2: CEP conhecido pelos testes do AccountForm.
export const VIACEP_KNOWN_CEP = "01310-100";

export const handlers = [
  http.get(`https://viacep.com.br/ws/:cep/json/`, ({ params }) => {
    const digits = String(params.cep).replace(/\D/g, "");
    if (digits !== VIACEP_KNOWN_CEP.replace(/\D/g, "")) {
      return HttpResponse.json({ erro: true });
    }
    return HttpResponse.json({
      uf: "SP",
      localidade: "São Paulo",
      logradouro: "Av. Paulista",
      bairro: "Bela Vista",
    });
  }),

  http.post(`${BASE_URL}/api/v1/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    const tenantId = request.headers.get("X-Tenant-Id");

    if (
      tenantId !== validCredentials.tenantId ||
      body.email !== validCredentials.email ||
      body.password !== validCredentials.password
    ) {
      return unauthorized("/api/v1/auth/login", "E-mail ou senha inválidos.");
    }

    return HttpResponse.json({
      access_token: "access-token-1",
      refresh_token: "refresh-token-1",
      expires_in: 900,
    });
  }),

  http.post(`${BASE_URL}/api/v1/auth/refresh`, async ({ request }) => {
    if (!request.headers.get("X-Tenant-Id")) {
      return missingTenantId("/api/v1/auth/refresh");
    }

    refreshCallCount += 1;
    const body = (await request.json()) as { refresh_token: string };

    if (!VALID_REFRESH_TOKENS.has(body.refresh_token)) {
      return unauthorized("/api/v1/auth/refresh", "Refresh token inválido.");
    }

    return HttpResponse.json({
      access_token: "access-token-2",
      refresh_token: "refresh-token-2",
      expires_in: 900,
    });
  }),

  http.get(`${BASE_URL}/api/v1/auth/me`, ({ request }) => {
    const authorization = request.headers.get("Authorization") ?? "";
    const token = authorization.replace("Bearer ", "");

    if (!VALID_ACCESS_TOKENS.has(token)) {
      return unauthorized("/api/v1/auth/me", "Não autenticado.");
    }

    return HttpResponse.json(validUser);
  }),

  http.post(`${BASE_URL}/api/v1/auth/logout`, ({ request }) => {
    if (!request.headers.get("X-Tenant-Id")) {
      return missingTenantId("/api/v1/auth/logout");
    }
    return new HttpResponse(null, { status: 204 });
  }),

  // Handler base (spec 066): o `VariablePicker` do editor de modelos (spec 065)
  // busca isso sempre que monta — testes que não mockam `@/features/templates/api`
  // inteiro (ex.: TemplateEditorPage.test.tsx, que só sobrescreve get/updateTemplate)
  // caem aqui em vez de estourar "unhandled request".
  http.get(`${BASE_URL}/api/v1/template-variables`, () =>
    HttpResponse.json([
      { namespace: "cliente", key: "nome_completo", label: "Nome completo" },
      { namespace: "processo", key: "numero_cnj", label: "Número CNJ" },
      { namespace: "escritorio", key: "razao_social", label: "Razão social" },
      { namespace: "usuario", key: "nome", label: "Nome" },
    ]),
  ),
];
