// Tests del componente OrdenesFilters.
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrdenesFilters } from "../components/ordenes-compra/OrdenesFilters";

const noop = () => {};

describe("OrdenesFilters", () => {
  it("renderiza los 4 inputs de filtros (estado, proveedor, desde, hasta)", () => {
    render(
      <OrdenesFilters
        estadoFiltro=""
        setEstadoFiltro={noop}
        proveedorFiltro=""
        setProveedorFiltro={noop}
        fechaDesde=""
        setFechaDesde={noop}
        fechaHasta=""
        setFechaHasta={noop}
      />,
    );
    expect(screen.getByLabelText("Estado")).toBeInTheDocument();
    expect(screen.getByLabelText(/Proveedor/)).toBeInTheDocument();
    expect(screen.getByLabelText("Desde")).toBeInTheDocument();
    expect(screen.getByLabelText("Hasta")).toBeInTheDocument();
  });

  it("muestra el valor del filtro de estado seleccionado", () => {
    render(
      <OrdenesFilters
        estadoFiltro="borrador"
        setEstadoFiltro={noop}
        proveedorFiltro=""
        setProveedorFiltro={noop}
        fechaDesde=""
        setFechaDesde={noop}
        fechaHasta=""
        setFechaHasta={noop}
      />,
    );
    const select = screen.getByLabelText("Estado");
    expect(select).toHaveValue("borrador");
  });

  it("llama a setEstadoFiltro cuando cambia el select de estado", async () => {
    const user = userEvent.setup();
    const setEstadoFiltro = vi.fn();
    render(
      <OrdenesFilters
        estadoFiltro=""
        setEstadoFiltro={setEstadoFiltro}
        proveedorFiltro=""
        setProveedorFiltro={noop}
        fechaDesde=""
        setFechaDesde={noop}
        fechaHasta=""
        setFechaHasta={noop}
      />,
    );
    await user.selectOptions(screen.getByLabelText("Estado"), "aprobado");
    expect(setEstadoFiltro).toHaveBeenCalledWith("aprobado");
  });

  it("llama a setProveedorFiltro cuando el usuario escribe en el input", async () => {
    const user = userEvent.setup();
    const setProveedorFiltro = vi.fn();
    render(
      <OrdenesFilters
        estadoFiltro=""
        setEstadoFiltro={noop}
        proveedorFiltro=""
        setProveedorFiltro={setProveedorFiltro}
        fechaDesde=""
        setFechaDesde={noop}
        fechaHasta=""
        setFechaHasta={noop}
      />,
    );
    await user.type(screen.getByLabelText(/Proveedor/), "Acme");
    expect(setProveedorFiltro).toHaveBeenCalled();
  });
});
