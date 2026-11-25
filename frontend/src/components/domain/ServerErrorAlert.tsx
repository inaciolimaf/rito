import { describeApiErrors } from "@/components/domain/apiErrors";
import type { ApiError } from "@/lib/errors";

export interface ServerErrorAlertProps {
  error: ApiError | null | undefined;
}

/** O erro do servidor que o formulário não conseguiu prender num campo.
 *
 * Spec 138, regra 5: antes, o alerta geral só aparecia quando `errors` vinha vazio — ou
 * seja, sumia justamente nos casos em que o servidor tinha mais a dizer (a lista de
 * critérios da política de senha, a regra de jornada que vale para o formulário inteiro).
 * A regra agora é a óbvia: **toda** mensagem sem campo aparece, e um 422 que não produziu
 * nenhum erro de campo sempre mostra pelo menos o `detail`. */
export function ServerErrorAlert({ error }: ServerErrorAlertProps): JSX.Element | null {
  if (!error) return null;
  const { fields, messages } = describeApiErrors(error);
  // Com erro de campo e nada mais a dizer, o alerta geral seria ruído: a mensagem já
  // está embaixo do campo que a causou.
  if (fields.length > 0 && messages.length === 0) return null;

  return (
    <div role="alert" className="space-y-1 text-sm text-danger">
      {error.message && <p>{error.message}</p>}
      {messages.length > 0 && (
        <ul className="list-disc pl-5">
          {messages.map((message, index) => (
            <li key={`${message}-${index}`}>{message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
