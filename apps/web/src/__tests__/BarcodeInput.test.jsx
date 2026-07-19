/**
 * Tests de BarcodeInput (Fase 2).
 *
 * Cubre:
 * - Dispara onScan al hacer Enter con buffer >= 6 chars.
 * - No dispara con buffer < 6 chars.
 * - Throttle: reset del buffer tras > 100ms entre teclas.
 * - Accesibilidad: aria-label + role="searchbox".
 *
 * Requiere: vitest + @testing-library/react + @testing-library/user-event + jsdom.
 * (No instalados todavía por restricción de Fase 2 — ver doc de la fase.)
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BarcodeInput } from "../components/BarcodeInput";

describe("BarcodeInput", () => {
  it("dispara onScan al hacer Enter con buffer >= 6 chars", async () => {
    const onScan = vi.fn();
    render(<BarcodeInput onScan={onScan} />);
    const input = screen.getByRole("searchbox");

    // Simulamos tipeo rapido de un scanner (< 100ms entre teclas)
    await userEvent.type(input, "1234567", { delay: 10 });
    await userEvent.keyboard("{Enter}");

    expect(onScan).toHaveBeenCalledTimes(1);
    expect(onScan).toHaveBeenCalledWith("1234567");
  });

  it("NO dispara onScan si el buffer tiene < 6 chars", async () => {
    const onScan = vi.fn();
    render(<BarcodeInput onScan={onScan} />);
    const input = screen.getByRole("searchbox");

    await userEvent.type(input, "12345", { delay: 10 });
    await userEvent.keyboard("{Enter}");

    expect(onScan).not.toHaveBeenCalled();
  });

  it("resetea el buffer tras una pausa > 100ms entre teclas", async () => {
    const onScan = vi.fn();
    render(<BarcodeInput onScan={onScan} />);
    const input = screen.getByRole("searchbox");

    await userEvent.type(input, "ABCDE", { delay: 5 });
    await new Promise((r) => setTimeout(r, 150));
    await userEvent.type(input, "12345", { delay: 5 });
    await userEvent.keyboard("{Enter}");

    // Solo el segundo chunk cuenta (5 chars < 6 -> no dispara)
    expect(onScan).not.toHaveBeenCalled();
  });

  it("es accesible: tiene aria-label y role=searchbox", () => {
    render(<BarcodeInput onScan={() => {}} ariaLabel="Mi scanner" />);
    const input = screen.getByLabelText("Mi scanner");
    expect(input).toBeInTheDocument();
    expect(input.getAttribute("role")).toBe("searchbox");
  });
});
