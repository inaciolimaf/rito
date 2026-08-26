import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { CopilotPanel } from "@/features/ai/CopilotPanel";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

function withCopilot(options: { configured?: boolean; enabled?: boolean } = {}): void {
  const { configured = true, enabled = true } = options;
  server.use(
    http.get(`${BASE_URL}/api/v1/ai/feature-config`, () =>
      HttpResponse.json({
        items: [
          {
            feature_key: "copilot",
            label: "Copiloto",
            description: "Assistente",
            model: "fabricante-x/modelo-y",
            fallback_model: null,
            temperature: 0.2,
            max_tokens: null,
            is_enabled: enabled,
            store_prompts: false,
            is_default: false,
          },
        ],
        is_configured: configured,
        default_model: "fabricante-x/modelo-y",
      }),
    ),
    http.get(`${BASE_URL}/api/v1/ai/copilot/suggestions`, () =>
      HttpResponse.json({ items: ["O que é mais urgente hoje?"] }),
    ),
    http.get(`${BASE_URL}/api/v1/ai/copilot/threads`, () =>
      HttpResponse.json({ items: [], total: 0 }),
    ),
    http.post(`${BASE_URL}/api/v1/ai/copilot/message`, () =>
      HttpResponse.json({
        thread_id: "thread-1",
        title: "quantos prazos?",
        status: "done",
        reply: "Você tem 3 prazos esta semana.",
        pending_action: null,
        tool_labels: ["consultando tarefas"],
        model: null,
      }),
    ),
  );
}

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/home"]}>
        <CopilotPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CopilotPanel", () => {
  afterEach(() => server.resetHandlers());

  it("Ctrl+K abre e fecha o painel (spec 085 §6)", async () => {
    withCopilot();
    const user = userEvent.setup();
    renderPanel();
    await screen.findByLabelText("Abrir o copiloto (Ctrl+K)");

    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByTestId("copilot-panel")).toBeInTheDocument();

    await user.keyboard("{Control>}k{/Control}");
    await waitFor(() => expect(screen.queryByTestId("copilot-panel")).not.toBeInTheDocument());
  });

  it("mostra o que o agente consultou, em português, junto da resposta (regra 3)", async () => {
    withCopilot();
    const user = userEvent.setup();
    renderPanel();
    await screen.findByLabelText("Abrir o copiloto (Ctrl+K)");
    await user.keyboard("{Control>}k{/Control}");

    await user.type(await screen.findByLabelText("Pergunte ao copiloto"), "quantos prazos?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));

    expect(await screen.findByTestId("tool-call-indicator")).toHaveTextContent(
      "consultando tarefas",
    );
    expect(screen.getByTestId("chat-message-assistant")).toHaveTextContent(
      "Você tem 3 prazos esta semana.",
    );
  });

  it("sem chave de IA configurada, o botão nem aparece (regra 10)", async () => {
    withCopilot({ configured: false });
    renderPanel();

    await waitFor(() =>
      expect(screen.queryByLabelText("Abrir o copiloto (Ctrl+K)")).not.toBeInTheDocument(),
    );
  });
});
