import { describe, expect, it } from "vitest";

import { safeExternalHref } from "@/lib/urls";

describe("safeExternalHref (spec 138, regra 2)", () => {
  it("aceita http e https", () => {
    expect(safeExternalHref("https://comunica.pje.jus.br/x")).toBe("https://comunica.pje.jus.br/x");
    expect(safeExternalHref("http://tjsp.jus.br/a?b=1")).toBe("http://tjsp.jus.br/a?b=1");
    expect(safeExternalHref("https://wa.me/5511999998888")).toBe("https://wa.me/5511999998888");
  });

  it("recusa javascript:, data: e vbscript: — o link some em vez de virar código", () => {
    // O `link` da publicação vem verbatim do DJEN; o React 18 renderiza estes três sem
    // reclamar, e o clique executa na nossa origem.
    expect(safeExternalHref("javascript:alert(document.cookie)")).toBeUndefined();
    expect(safeExternalHref("  JaVaScRiPt:alert(1)  ")).toBeUndefined();
    expect(safeExternalHref("data:text/html,<script>alert(1)</script>")).toBeUndefined();
    expect(safeExternalHref("vbscript:msgbox(1)")).toBeUndefined();
  });

  it("recusa vazio, nulo e caminho relativo", () => {
    expect(safeExternalHref(null)).toBeUndefined();
    expect(safeExternalHref(undefined)).toBeUndefined();
    expect(safeExternalHref("   ")).toBeUndefined();
    expect(safeExternalHref("/lawsuits/1")).toBeUndefined();
  });
});
