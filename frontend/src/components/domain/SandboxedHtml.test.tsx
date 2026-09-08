import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SandboxedHtml } from "@/components/domain/SandboxedHtml";

describe("SandboxedHtml (spec 138, regra 1)", () => {
  it("põe o HTML num iframe sandbox, não no documento da aplicação", () => {
    const hostil = '<p>Dos fatos.</p><img src="x" onerror="window.roubou = true">';
    const { container } = render(<SandboxedHtml html={hostil} title="Minuta gerada" />);

    const frame = screen.getByTitle("Minuta gerada");
    expect(frame.tagName).toBe("IFRAME");
    // `sandbox=""` — sem `allow-scripts` e sem `allow-same-origin`. É o navegador que
    // garante que nada executa e que o documento não enxerga o localStorage da app.
    expect(frame).toHaveAttribute("sandbox", "");
    expect(frame.getAttribute("srcdoc")).toContain("Dos fatos.");

    // O conteúdo não é filho do nosso DOM: nenhum <img> hostil foi montado aqui.
    expect(container.querySelector("img")).toBeNull();
  });

  it("não permite escapar do sandbox por allow-scripts + allow-same-origin", () => {
    render(<SandboxedHtml html="<p>x</p>" title="Minuta" />);
    const sandbox = screen.getByTitle("Minuta").getAttribute("sandbox") ?? "";
    expect(sandbox).not.toContain("allow-scripts");
    expect(sandbox).not.toContain("allow-same-origin");
  });
});
