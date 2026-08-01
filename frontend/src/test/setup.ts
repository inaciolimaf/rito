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

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  resetMswState();
  setSession(null);
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterAll(() => server.close());
