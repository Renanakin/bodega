// Helpers de formato y conversion de fechas.

export function formatNum(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
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

// Input type=date emite 'YYYY-MM-DD'; lo convertimos a ISO completo.
// Para fecha_desde usamos 00:00 y para fecha_hasta 23:59:59 (server side).
export function toIsoDate(value) {
  if (!value) return undefined;
  return new Date(`${value}T00:00:00`).toISOString();
}
