import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ThemeToggle } from "@/components/ThemeToggle";
import { ThemeProvider } from "@/providers/ThemeProvider";

describe("ThemeToggle", () => {
  it("alterna o tema e persiste em localStorage", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );

    const button = screen.getByRole("button", { name: "Alternar tema" });
    const initiallyDark = document.documentElement.classList.contains("dark");

    await user.click(button);

    const isDarkNow = document.documentElement.classList.contains("dark");
    expect(isDarkNow).toBe(!initiallyDark);
    expect(localStorage.getItem("rito.theme")).toBe(isDarkNow ? "dark" : "light");
  });
});
