import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { StateCitySelect } from "@/features/customers/StateCitySelect";

vi.mock("@/features/locations/api", () => ({
  listStates: vi.fn().mockResolvedValue([
    { code: "SP", name: "São Paulo", ibge_code: 35 },
    { code: "RJ", name: "Rio de Janeiro", ibge_code: 33 },
  ]),
  listCities: vi
    .fn()
    .mockResolvedValue([{ ibge_code: 3550308, name: "São Paulo", state_code: "SP" }]),
}));

interface FormValues {
  state: string;
  city: string;
}

function Harness(): JSX.Element {
  const { control, setValue, watch } = useForm<FormValues>({
    defaultValues: { state: "SP", city: "São Paulo" },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return (
    <QueryClientProvider client={queryClient}>
      <StateCitySelect
        control={control}
        setValue={setValue}
        stateName="state"
        cityName="city"
        stateValue={watch("state")}
        cityValue={watch("city")}
      />
    </QueryClientProvider>
  );
}

describe("StateCitySelect", () => {
  it("trocar estado limpa cidade", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: "São Paulo" })).toBeInTheDocument(),
    );
    expect(screen.getByRole("list", { name: "Selecionados" })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Estado"), "RJ");

    expect(screen.queryByRole("list", { name: "Selecionados" })).not.toBeInTheDocument();
  });
});
