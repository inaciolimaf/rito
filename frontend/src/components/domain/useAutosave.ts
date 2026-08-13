import * as React from "react";

export type AutosaveStatus = "idle" | "saving" | "saved" | "error";

export interface UseAutosaveOptions {
  /** Regra 2 (spec 065): debounce — grava só depois de parar de mudar, nunca a cada
   * tecla. */
  delayMs?: number;
  enabled?: boolean;
}

/** Debounce + grava automaticamente quando `value` muda — extraído do editor de
 * modelos (spec 065) para qualquer tela futura que precise do mesmo padrão (regra
 * dos 3 usos: hoje só um uso, mas o hook já nasce genérico por não ter nada
 * específico de modelo). Falha de gravação (regra 3) nunca descarta `value` — ele
 * continua vindo de fora (controlado pelo chamador), o hook só reporta o status. */
export function useAutosave<T>(
  value: T,
  save: (value: T) => Promise<void>,
  { delayMs = 2000, enabled = true }: UseAutosaveOptions = {},
): AutosaveStatus {
  const [status, setStatus] = React.useState<AutosaveStatus>("idle");
  const savedValueRef = React.useRef(value);
  const wasEnabledRef = React.useRef(enabled);
  const saveRef = React.useRef(save);
  saveRef.current = save;

  React.useEffect(() => {
    // `enabled` passa de false pra true quando os dados ainda estão carregando (ex.:
    // `draft` só existe depois do GET) — esse primeiro valor "carregado" não é uma
    // mudança do usuário, só sincroniza a base de comparação (sem isso, o autosave
    // dispararia um PUT supérfluo assim que a tela abrisse).
    if (enabled && !wasEnabledRef.current) {
      savedValueRef.current = value;
    }
    wasEnabledRef.current = enabled;

    if (!enabled || value === savedValueRef.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      setStatus("saving");
      saveRef
        .current(value)
        .then(() => {
          savedValueRef.current = value;
          setStatus("saved");
        })
        .catch(() => {
          setStatus("error");
        });
    }, delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs, enabled]);

  return status;
}
