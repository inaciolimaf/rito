import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PriorityBadge } from "@/features/posts/PriorityBadge";

describe("PriorityBadge", () => {
  it("mostra os badges combináveis de urgente, importante e privada (regra 10)", () => {
    render(<PriorityBadge isImportant isUrgent isPrivate />);

    expect(screen.getByLabelText("Urgente")).toBeInTheDocument();
    expect(screen.getByLabelText("Importante")).toBeInTheDocument();
    expect(screen.getByText("Privada")).toBeInTheDocument();
  });

  it("urgente e importante são independentes", () => {
    render(<PriorityBadge isUrgent />);

    expect(screen.getByLabelText("Urgente")).toBeInTheDocument();
    expect(screen.queryByLabelText("Importante")).not.toBeInTheDocument();
    expect(screen.queryByText("Privada")).not.toBeInTheDocument();
  });

  it("sem flags não renderiza nada", () => {
    const { container } = render(<PriorityBadge />);
    expect(container).toBeEmptyDOMElement();
  });
});
