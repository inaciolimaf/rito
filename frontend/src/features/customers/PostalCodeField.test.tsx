import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { PostalCodeField } from "@/features/customers/PostalCodeField";

vi.mock("@/lib/cep", () => ({
  lookupCep: vi.fn().mockResolvedValue({
    state: "SP",
    city: "São Paulo",
    street: "Praça da Sé",
    region: "Sé",
  }),
}));

interface FormValues {
  postal_code: string;
}

function Harness({ onFound }: { onFound: (result: unknown) => void }): JSX.Element {
  const { control } = useForm<FormValues>({ defaultValues: { postal_code: "" } });
  return <PostalCodeField control={control} name="postal_code" onFound={onFound} />;
}

describe("PostalCodeField", () => {
  it("CEP preenche endereço ao completar os 8 dígitos", async () => {
    const onFound = vi.fn();
    const user = userEvent.setup();
    render(<Harness onFound={onFound} />);

    await user.type(screen.getByLabelText("CEP"), "01310100");

    expect(screen.getByLabelText("CEP")).toHaveValue("01310-100");
    await waitFor(() =>
      expect(onFound).toHaveBeenCalledWith({
        state: "SP",
        city: "São Paulo",
        street: "Praça da Sé",
        region: "Sé",
      }),
    );
  });
});
