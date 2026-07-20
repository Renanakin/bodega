// Helpers de formato compartidos por Ordenes de Compra.

export function formatCLP(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  });
}

export function formatFecha(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("es-CL", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}
