import "@testing-library/jest-dom/vitest";

import { afterAll, afterEach, beforeAll } from "vitest";

import { setSession } from "@/lib/api";
import { resetMswState } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

// jsdom não implementa matchMedia — ThemeProvider precisa dele para ler a preferência do SO.
// as unknown: o polyfill só cobre os campos que o código de produção realmente lê;
// um MediaQueryList completo exigiria stubs sem uso real neste teste.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// jsdom não implementa layout — Range não tem getClientRects/getBoundingClientRect,
// que o ProseMirror (TipTap, spec 065) usa para posicionar o cursor/rolar a tela ao
// focar. Sem isso, qualquer teste que seleciona texto antes de aplicar uma marca
// (negrito etc.) derruba o editor com "target.getClientRects is not a function".
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
}
if (!Range.prototype.getBoundingClientRect) {
  Range.prototype.getBoundingClientRect = () =>
    ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0 }) as DOMRect;
}
// mesma lacuna de layout: clicar dentro do editor consulta `elementFromPoint` para
// achar a posição do cursor pelo mouse.
if (!document.elementFromPoint) {
  document.elementFromPoint = () => null;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  resetMswState();
  setSession(null);
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterAll(() => server.close());
