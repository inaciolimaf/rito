import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { SettingsHubPage } from "@/features/settings/SettingsHubPage";
import { SETTINGS_SECTIONS } from "@/features/settings/settingsSections";

const mockUseAuth = vi.fn();
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderHub(capabilities: string[]): void {
  mockUseAuth.mockReturnValue({ user: { id: "u1", role: "GESTOR", capabilities } });
  render(
    <MemoryRouter>
      <SettingsHubPage />
    </MemoryRouter>,
  );
}

describe("SettingsHubPage (spec 102, regra 16)", () => {
  it("lista os grupos e leva a cada tela de configuração", () => {
    renderHub(["settings.manage", "financial.read"]);

    for (const section of SETTINGS_SECTIONS) {
      expect(screen.getByText(section.title)).toBeInTheDocument();
    }
    // Cada link aponta para a rota declarada na fonte única, não para um href escrito
    // à mão no JSX.
    for (const section of SETTINGS_SECTIONS) {
      for (const link of section.links) {
        expect(screen.getByRole("link", { name: new RegExp(link.label) })).toHaveAttribute(
          "href",
          link.path,
        );
      }
    }
  });

  it("esconde o que a capability não permite", () => {
    // Sem `financial.read`: o grupo Financeiro fica sem nenhum link e some inteiro, em
    // vez de aparecer vazio.
    renderHub(["settings.manage"]);

    expect(screen.queryByRole("link", { name: /Plano de contas/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Financeiro")).not.toBeInTheDocument();
    // O resto continua lá.
    expect(screen.getByRole("link", { name: /Usuários/ })).toBeInTheDocument();
  });

  it("cobre todas as telas de configuração que existem em App.tsx", async () => {
    // Regra 16: o hub existe para que nenhuma tela de configuração fique alcançável só
    // por URL direta (era a dívida nº 10). Se alguém criar uma rota /settings/* nova e
    // esquecer de listá-la aqui, o hub deixa de cumprir o que promete — e este teste
    // avisa, em vez de a tela sumir do produto em silêncio.
    const { readFile } = await import("node:fs/promises");
    const { resolve } = await import("node:path");
    const appTsx = await readFile(resolve(process.cwd(), "src/App.tsx"), "utf-8");
    const rotasDeConfig = [...appTsx.matchAll(/path="(\/settings\/[^"]+)"/g)]
      .map((match) => match[1] as string)
      // Rotas de detalhe (com parâmetro) não são "telas" para o hub.
      .filter((rota) => !rota.includes(":"));

    const noHub = new Set(SETTINGS_SECTIONS.flatMap((s) => s.links.map((l) => l.path)));
    const faltando = rotasDeConfig.filter((rota) => !noHub.has(rota));

    expect(faltando).toEqual([]);
  });
});
