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

  constructor(problem: ProblemDetail) {
    super(problem.detail);
    this.name = "ApiError";
    this.status = problem.status;
    this.title = problem.title;
    this.type = problem.type;
    this.instance = problem.instance;
    this.errors = problem.errors;
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
