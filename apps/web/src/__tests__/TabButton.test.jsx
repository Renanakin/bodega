// Tests del componente TabButton (settings + reports).
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TabButton } from "../components/settings/TabButton";

describe("TabButton", () => {
  it("aplica estilos activos cuando active=true", () => {
    render(<TabButton active onClick={() => {}}>Reglas</TabButton>);
    const btn = screen.getByRole("tab", { name: /Reglas/ });
    expect(btn).toHaveAttribute("aria-selected", "true");
    expect(btn.className).toMatch(/border-indigo-600/);
  });

  it("aplica estilos inactivos cuando active=false", () => {
    render(<TabButton active={false} onClick={() => {}}>Reglas</TabButton>);
    const btn = screen.getByRole("tab", { name: /Reglas/ });
    expect(btn).toHaveAttribute("aria-selected", "false");
    expect(btn.className).toMatch(/border-transparent/);
  });

  it("ejecuta onClick al hacer click", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<TabButton active onClick={onClick}>Reglas</TabButton>);
    await user.click(screen.getByRole("tab", { name: /Reglas/ }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
