/**
 * Tests de SearchSku (Fase 2).
 *
 * Cubre:
 * - Debounce 300ms antes de llamar fetch.
 * - Muestra resultados en dropdown.
 * - onSelect al hacer click en un item.
 *
 * Requiere: vitest + @testing-library/react + @testing-library/user-event + jsdom.
 * (No instalados todavía por restricción de Fase 2 — ver doc de la fase.)
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchSku } from "../components/SearchSku";

function mockFetch(payload) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(payload),
    }),
  );
}

describe("SearchSku", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("NO llama a fetch antes del debounce de 300ms", async () => {
    const fetchSpy = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve([]),
      }),
    );
    globalThis.fetch = fetchSpy;

    render(<SearchSku onSelect={() => {}} />);
    const input = screen.getByRole("combobox");

    await userEvent.type(input, "ACE");

    expect(fetchSpy).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(300);
    });
    await Promise.resolve();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][0]).toMatch(/\/products\?sku=ACE/);
  });

  it("muestra resultados y llama onSelect al elegir uno", async () => {
    mockFetch([{ id: "p1", sku: "ACE-001", name: "Aceite" }]);
    const onSelect = vi.fn();

    render(<SearchSku onSelect={onSelect} autoFocus={false} />);
    const input = screen.getByRole("combobox");

    await userEvent.type(input, "ACE");
    act(() => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByText("ACE-001")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("ACE-001"));

    expect(onSelect).toHaveBeenCalledWith({
      id: "p1",
      sku: "ACE-001",
      name: "Aceite",
    });
  });
});
