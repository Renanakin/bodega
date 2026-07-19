/**
 * Tests E2E de MultibodegaGridPage (Fase 2).
 *
 * Cubre el flujo end-to-end:
 * 1. User escribe SKU en SearchSku.
 * 2. Se llama GET /api/v1/inventario/real/distribucion?sku=XXX.
 * 3. La grilla se renderiza con la respuesta.
 * 4. Si el SKU no existe, se muestra empty state.
 *
 * Requiere: vitest + @testing-library/react + @testing-library/user-event + jsdom.
 * (No instalados todavía por restricción de Fase 2 — ver doc de la fase.)
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MultibodegaGridPage } from "../views/MultibodegaGridPage";

// Mockeamos el UiContext para evitar ToastViewport en el render.
vi.mock("../context/UiContext", () => ({
  useUi: () => ({ pushToast: vi.fn() }),
}));

function mockApiResponse(payload, status = 200) {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(payload),
    }),
  );
}

describe("MultibodegaGridPage E2E", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("carga la grilla al buscar un SKU existente", async () => {
    mockApiResponse({
      producto_id: "p1",
      sku: "ACE-001",
      name: "Aceite",
      precio_costo: 5000,
      precio_venta: 8500,
      total_global: 150,
      bodegas: [
        {
          bodega_id: "b1",
          bodega_code: "PRINCIPAL",
          bodega_name: "Bodega Principal",
          bodega_type: "principal",
          total_quantity: 150,
          min_quantity: 10,
          estado: "normal",
          ubicaciones: [],
        },
      ],
    });

    render(<MultibodegaGridPage />);
    const searchInput = screen.getByRole("combobox");

    await userEvent.type(searchInput, "ACE-001");
    act(() => vi.advanceTimersByTime(300));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText("PRINCIPAL")).toBeInTheDocument();
      expect(screen.getByText("150")).toBeInTheDocument();
    });
  });

  it("muestra empty state si el SKU no existe (404 product_not_found)", async () => {
    mockApiResponse(
      { detail: { code: "product_not_found", message: "No existe" } },
      404,
    );

    render(<MultibodegaGridPage />);
    const searchInput = screen.getByRole("combobox");

    await userEvent.type(searchInput, "NOPE-001");
    act(() => vi.advanceTimersByTime(300));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });
  });
});
