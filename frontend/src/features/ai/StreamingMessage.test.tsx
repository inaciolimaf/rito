import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StreamingMessage } from "@/features/ai/StreamingMessage";

describe("StreamingMessage", () => {
  it("concatena os pedaços recebidos, na ordem (spec 085, regra 2)", () => {
    const { rerender } = render(<StreamingMessage chunks={["Você tem "]} isStreaming />);
    expect(screen.getByTestId("streaming-message")).toHaveTextContent("Você tem");

    rerender(<StreamingMessage chunks={["Você tem ", "3 prazos ", "esta semana."]} isStreaming />);
    expect(screen.getByTestId("streaming-message")).toHaveTextContent(
      "Você tem 3 prazos esta semana.",
    );
    // Enquanto flui, o cursor mostra que ainda vem mais.
    expect(screen.getByTestId("streaming-caret")).toBeInTheDocument();
  });

  it("quando termina, o cursor some", () => {
    render(<StreamingMessage chunks={["Pronto."]} isStreaming={false} />);

    expect(screen.getByTestId("streaming-message")).toHaveTextContent("Pronto.");
    expect(screen.queryByTestId("streaming-caret")).not.toBeInTheDocument();
  });
});
