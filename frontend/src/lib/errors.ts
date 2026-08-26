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
