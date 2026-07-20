// Tests del componente Timeline (ordenes-compra).
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Timeline } from "../components/ordenes-compra/Timeline";

describe("Timeline", () => {
  it("renderiza solo 'Borrador' cuando estado es borrador", () => {
    render(<Timeline estado="borrador" />);
    expect(screen.getByText("Borrador")).toBeInTheDocument();
  });

  it("renderiza pasos progresivos cuando estado es aprobado", () => {
    render(<Timeline estado="aprobado" />);
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(screen.getByText("Enviado a supervisor")).toBeInTheDocument();
    expect(screen.getByText("Aprobado")).toBeInTheDocument();
  });

  it("muestra fechas cuando se pasan como props", () => {
    render(
      <Timeline
        estado="received"
        email_enviado_at="2026-01-15T10:00:00Z"
        aprobado_at="2026-01-16T12:00:00Z"
        comprado_at={null}
      />,
    );
    expect(screen.getByText(/Email enviado:/)).toBeInTheDocument();
    expect(screen.getByText(/Aprobado:/)).toBeInTheDocument();
    // comprado_at es null, no debe mostrarse
    expect(screen.queryByText(/Comprado:/)).not.toBeInTheDocument();
  });

  it("cae a 'Borrador' cuando el estado no existe en el mapa", () => {
    render(<Timeline estado="estado_inexistente" />);
    // Solo el fallback "Borrador"
    expect(screen.getByText("Borrador")).toBeInTheDocument();
  });
});
