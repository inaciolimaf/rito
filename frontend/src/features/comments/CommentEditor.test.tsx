import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CommentEditor } from "@/features/comments/CommentEditor";

const MENTIONABLE = [
  { id: "u1", name: "Marina Costa" },
  { id: "u2", name: "Marcos Paulo" },
];

describe("CommentEditor — autocomplete de @", () => {
  it("digitar @ seguido de letras sugere usuários e escolher insere o nome", async () => {
    const user = userEvent.setup();
    const onSearchMentions = vi.fn(async (query: string) =>
      MENTIONABLE.filter((option) => option.name.toLowerCase().includes(query.toLowerCase())),
    );
    const onSubmit = vi.fn(async () => {});

    render(<CommentEditor onSearchMentions={onSearchMentions} onSubmit={onSubmit} />);

    const textarea = screen.getByLabelText("Comentário");
    await user.type(textarea, "bom dia @Mar");

    await waitFor(() => expect(onSearchMentions).toHaveBeenCalledWith("Mar"));
    const option = await screen.findByRole("option", { name: "Marina Costa" });
    await user.click(option);

    // Escolher insere "@Nome Completo " no lugar do token parcial.
    expect(textarea).toHaveValue("bom dia @Marina Costa ");

    await user.click(screen.getByRole("button", { name: "Comentar" }));
    expect(onSubmit).toHaveBeenCalledWith("bom dia @Marina Costa");
  });

  it("fora de um token @ não abre sugestões (e-mail não é menção)", async () => {
    const user = userEvent.setup();
    const onSearchMentions = vi.fn(async () => MENTIONABLE);

    render(<CommentEditor onSearchMentions={onSearchMentions} onSubmit={async () => {}} />);

    await user.type(screen.getByLabelText("Comentário"), "escreva para maria@exemplo");

    await waitFor(() => {
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });
    expect(onSearchMentions).not.toHaveBeenCalled();
  });
});
