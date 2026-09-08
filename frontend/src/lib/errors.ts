export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  errors?: unknown[];
}

/** Erro tipado a partir de uma resposta RFC 7807 (application/problem+json). */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly type: string;
  readonly instance: string;
  readonly errors?: unknown[];
  /** Membros de extensão do problem+json (RFC 7807 §3.2): o backend usa isso para
   * mandar dado estruturado junto do erro — o primeiro caso é a dúvida do text-to-SQL
   * (spec 089, regra 1). Sem guardar, a informação chegaria e seria descartada aqui. */
  readonly extensions: Record<string, unknown>;

  constructor(problem: ProblemDetail) {
    super(problem.detail);
    this.name = "ApiError";
    this.status = problem.status;
    this.title = problem.title;
    this.type = problem.type;
    this.instance = problem.instance;
    this.errors = problem.errors;
    const standard = new Set(["type", "title", "status", "detail", "instance", "errors"]);
    this.extensions = Object.fromEntries(
      Object.entries(problem as unknown as Record<string, unknown>).filter(
        ([key]) => !standard.has(key),
      ),
    );
  }
}

function isProblemDetail(value: unknown): value is ProblemDetail {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    "title" in value &&
    "detail" in value
  );
}

/** Converte o corpo de uma resposta HTTP não-ok (já parseado ou não) num ApiError. */
export async function toApiError(response: Response, path: string): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  if (isProblemDetail(body)) {
    return new ApiError(body);
  }
  return new ApiError({
    type: "about:blank",
    title: "Erro",
    status: response.status,
    detail: "Não foi possível completar a requisição.",
    instance: path,
  });
}

export type FailureKind = "forbidden" | "not-found" | "offline" | "server";

export interface FailureDescription {
  kind: FailureKind;
  title: string;
  description: string;
}

/** Spec 138, regras 4 e 9: uma falha de leitura vira texto para o usuário aqui, num
 * lugar só. O 403 é o caso que motivou a função: como os filtros vivem na URL e o link
 * é compartilhável (CLAUDE.md §6), receber um link de uma área a que não se tem acesso é
 * rotina — e "Não foi possível carregar os dados." manda a pessoa recarregar para sempre
 * em vez de dizer que o problema é permissão. */
export function describeFailure(error: unknown): FailureDescription {
  if (error instanceof ApiError && error.status === 403) {
    return {
      kind: "forbidden",
      title: "Você não tem acesso a esta área.",
      description: "Seu perfil não permite ver estes dados. Peça a um gestor para liberar.",
    };
  }
  if (error instanceof ApiError && error.status === 404) {
    return {
      kind: "not-found",
      title: "Não encontramos este registro.",
      description: "Ele pode ter sido excluído, ou o endereço está incorreto.",
    };
  }
  if (error instanceof ApiError) {
    return { kind: "server", title: "Não foi possível carregar.", description: error.message };
  }
  return {
    kind: "offline",
    title: "Não foi possível carregar.",
    description: "Verifique sua conexão e tente de novo.",
  };
}

/** A mesma falha em uma linha só, para onde não cabe um bloco (a faixa de erro do
 * `DataTable`, por exemplo). */
export function failureMessage(error: unknown): string {
  const { kind, title, description } = describeFailure(error);
  return kind === "server" ? description : `${title} ${description}`;
}
