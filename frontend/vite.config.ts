import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    css: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/mocks/**"],
      // Spec 117, regras 3 e 7: piso = valor MEDIDO (53,98% de statements em
      // 01/09/2026, já com as extrações da 119), arredondado para baixo. Que ele
      // comece em 53 é um fato, não um endosso — o backend está em 91 e o frontend é
      // o lado que ninguém estava olhando. Piso é piso: sobe quando a medição sobe,
      // nunca desce; baixar exige spec própria, igual ao orçamento de wall-clock.
      //
      // Só morde em `npm run test:coverage`, o passo próprio de cobertura no CI. O
      // `make test` roda `npm run test`, sem instrumentação, e não paga por isto.
      //
      // Branches (75,21%) e functions (51,56%) são medidos e publicados no resumo do
      // CI, mas não são gate: §6 da spec deixa fora — ligar dois números novos ao
      // mesmo tempo é um a mais do que dá para defender.
      thresholds: {
        statements: 53,
        lines: 53,
      },
    },
  },
});
