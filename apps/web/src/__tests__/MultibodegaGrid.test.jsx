/**
 * Tests de MultibodegaGrid (Fase 2).
 *
 * Cubre:
 * - Renderiza el formato spec §4.1 con bodegas y cantidades.
 * - Muestra badge ALERTA en bodegas bajo mínimo.
 * - Muestra estado vacío si distribucion es null.
 * - Muestra loading skeleton.
 * - Muestra mensaje de error.
 *
 * Requiere: vitest + @testing-library/react + jsdom.
 * (No instalados todavía por restricción de Fase 2 — ver doc de la fase.)
 */
import { render, screen } from "@testing-library/react";
import { MultibodegaGrid } from "../components/MultibodegaGrid";

const distSample = {
  producto_id: "p1",
  sku: "ACE-001",
  name: "Aceite motor 5W30",
  precio_costo: 5000,
  precio_venta: 8500,
  total_global: 170,
  bodegas: [
    {
      bodega_id: "b1",
      bodega_code: "PRINCIPAL",
      bodega_name: "Bodega Principal",
      bodega_type: "principal",
      total_quantity: 140,
      min_quantity: 10,
      estado: "normal",
      ubicaciones: [
        {
          id_ubicacion: "u1",
          pasillo: 1,
          estanteria: 2,
          altura: 1,
          cantidad: 140,
          code: "P-01/E-02/A-01",
        },
      ],
    },
    {
      bodega_id: "b2",
      bodega_code: "AUX-1",
      bodega_name: "Auxiliar 1",
      bodega_type: "auxiliar",
      total_quantity: 3,
      min_quantity: 10,
      estado: "alerta",
      ubicaciones: [],
    },
  ],
};

describe("MultibodegaGrid", () => {
  it("renderiza la distribución con el formato spec", () => {
    render(<MultibodegaGrid distribucion={distSample} />);
    expect(screen.getByText("PRINCIPAL")).toBeInTheDocument();
    expect(screen.getByText("AUX-1")).toBeInTheDocument();
    expect(screen.getByText("140")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Total global:")).toBeInTheDocument();
    expect(screen.getByText("170")).toBeInTheDocument();
  });

  it("muestra badge ALERTA en bodegas bajo mínimo", () => {
    render(<MultibodegaGrid distribucion={distSample} />);
    const alerts = screen.getAllByText("ALERTA");
    expect(alerts.length).toBeGreaterThan(0);
  });

  it("muestra estado vacío si distribucion es null", () => {
    render(<MultibodegaGrid distribucion={null} />);
    expect(
      screen.getByText(/Selecciona un producto para ver/i),
    ).toBeInTheDocument();
  });

  it("muestra skeleton cuando loading=true", () => {
    const { container } = render(<MultibodegaGrid loading={true} />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("muestra mensaje de error si error esta presente", () => {
    render(<MultibodegaGrid error="Network failed" />);
    expect(screen.getByText("Network failed")).toBeInTheDocument();
  });
});
