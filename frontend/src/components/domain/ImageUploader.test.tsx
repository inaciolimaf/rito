import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ImageUploader } from "@/components/domain/ImageUploader";

const TEXTOS = {
  label: "Logotipo",
  alt: "Logotipo do escritório",
  emptyLabel: "Sem logo",
  uploadLabel: "Enviar logotipo",
  replaceLabel: "Trocar logotipo",
  replaceTitle: "Substituir logotipo?",
  replaceDescription: "O logotipo atual será substituído pelo novo arquivo.",
  oversizeError: "Logotipo acima de 2 MB.",
  uploadError: "Não foi possível enviar o logotipo.",
};

function renderUploader(props: Partial<React.ComponentProps<typeof ImageUploader>> = {}): {
  input: HTMLInputElement;
  onUpload: ReturnType<typeof vi.fn>;
} {
  const onUpload = vi.fn().mockResolvedValue(undefined);
  const { container } = render(
    <ImageUploader {...TEXTOS} imageUrl={null} onUpload={onUpload} {...props} />,
  );
  const input = container.querySelector('input[type="file"]');
  if (!(input instanceof HTMLInputElement)) throw new Error("input de arquivo não renderizou");
  return { input, onUpload };
}

/** `File` com tamanho controlado — jsdom calcula `size` a partir do conteúdo, e alocar
 * 2 MB de string só para o teste seria desperdício. */
function arquivo(nome: string, tipo: string, bytes: number): File {
  const file = new File(["x"], nome, { type: tipo });
  Object.defineProperty(file, "size", { value: bytes });
  return file;
}

describe("ImageUploader", () => {
  it("rejeita formato fora da allowlist sem chamar o upload", async () => {
    // `applyAccept: false` porque o seletor nativo já filtra por `accept` — o teste mira a
    // segunda barreira, a validação em código para quem escolhe "todos os arquivos".
    const user = userEvent.setup({ applyAccept: false });
    const { input, onUpload } = renderUploader();

    await user.upload(input, arquivo("contrato.pdf", "application/pdf", 1024));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Formato inválido — use PNG, JPG ou SVG.",
    );
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("rejeita arquivo acima do máximo sem chamar o upload", async () => {
    const user = userEvent.setup();
    const { input, onUpload } = renderUploader();

    await user.upload(input, arquivo("logo.png", "image/png", 3 * 1024 * 1024));

    expect(await screen.findByRole("alert")).toHaveTextContent("Logotipo acima de 2 MB.");
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("envia direto quando não há imagem, e pede confirmação quando já existe", async () => {
    const user = userEvent.setup();
    const { input, onUpload } = renderUploader();

    await user.upload(input, arquivo("logo.png", "image/png", 1024));
    await waitFor(() => expect(onUpload).toHaveBeenCalledOnce());

    const comImagem = renderUploader({ imageUrl: "https://exemplo/logo.png" });
    await user.upload(comImagem.input, arquivo("outro.png", "image/png", 1024));

    expect(await screen.findByText("Substituir logotipo?")).toBeInTheDocument();
    expect(comImagem.onUpload).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Substituir" }));
    await waitFor(() => expect(comImagem.onUpload).toHaveBeenCalledOnce());
  });

  it("o formato do preview segue a prop shape — logotipo quadrado, foto redonda", () => {
    const { container } = render(
      <ImageUploader {...TEXTOS} imageUrl="https://exemplo/logo.png" onUpload={vi.fn()} />,
    );
    expect(container.querySelector("img")).toHaveClass("rounded", "object-contain");

    const redondo = render(
      <ImageUploader
        {...TEXTOS}
        imageUrl="https://exemplo/foto.png"
        shape="circle"
        onUpload={vi.fn()}
      />,
    );
    expect(redondo.container.querySelector("img")).toHaveClass("rounded-full", "object-cover");
  });
});
