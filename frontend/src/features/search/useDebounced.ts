import * as React from "react";

/** Regra 7 da spec 096: 250 ms.
 *
 * O número não é estético: abaixo disso uma pessoa digitando "marina" dispara seis
 * buscas, e a resposta da terceira chega depois da quinta — a tela pisca resultados que
 * já não valem. Acima disso, a busca começa a parecer lenta. */
export function useDebounced<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = React.useState(value);

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
