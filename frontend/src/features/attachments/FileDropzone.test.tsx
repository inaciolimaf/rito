import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FileDropzone } from "@/features/attachments/FileDropzone";
import { MAX_ATTACHMENT_BYTES } from "@/features/attachments/rules";

function makeFile(name: string, size: number, type: string): File {
  const file = new File(["conteúdo"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("FileDropzone", () => {
  it("aceita PDF e recusa executável e arquivo acima de 50 MB (regra 5)", async () => {
    const user = userEvent.setup();
    const onFiles = vi.fn();

    render(<FileDropzone onFiles={onFiles} />);

    const input = screen.getByLabelText("Selecionar anexos");
    const ok = makeFile("peticao.pdf", 1024, "application/pdf");
    const exe = makeFile("virus.exe", 1024, "application/pdf"); // extensão denuncia
    const big = makeFile("grande.pdf", MAX_ATTACHMENT_BYTES + 1, "application/pdf");

    await user.upload(input, [ok, exe, big]);

    // Só o válido vai para o callback; os recusados viram mensagem de erro.
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0]?.[0]).toEqual([ok]);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("virus.exe: Tipo de arquivo não permitido.");
    expect(alert.textContent).toContain("grande.pdf: Anexo acima de 50 MB.");
  });
});
