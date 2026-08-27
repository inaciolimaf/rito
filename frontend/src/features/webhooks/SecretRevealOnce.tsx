import * as React from "react";

export interface SecretRevealOnceProps {
  secret: string;
  onDismiss: () => void;
}

/** O segredo do webhook, mostrado UMA vez (spec 093, regra 8).
 *
 * O componente é deliberadamente incômodo: ocupa espaço, exige confirmação explícita e
 * some para sempre. Quem fechar sem copiar precisa rotacionar — e é melhor assim do que
 * um segredo que fica pendurado na tela e acaba num print de suporte. */
export function SecretRevealOnce({ secret, onDismiss }: SecretRevealOnceProps): JSX.Element {
  const [copiado, setCopiado] = React.useState(false);

  return (
    <div
      role="alert"
      aria-label="Segredo do webhook"
      className="space-y-2 rounded border border-warning bg-warning/10 p-3"
    >
      <p className="text-sm">
        Guarde este segredo agora. Ele <strong>não será mostrado de novo</strong> — é com ele que o
        outro lado confere a assinatura de cada envio.
      </p>
      <code className="block break-all rounded bg-surface p-2 text-xs">{secret}</code>
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded border border-default px-2 py-1 text-xs"
          onClick={() => {
            void navigator.clipboard?.writeText(secret);
            setCopiado(true);
          }}
        >
          {copiado ? "Copiado" : "Copiar"}
        </button>
        <button
          type="button"
          className="rounded bg-primary px-2 py-1 text-xs text-on-primary"
          onClick={onDismiss}
        >
          Já guardei
        </button>
      </div>
    </div>
  );
}
