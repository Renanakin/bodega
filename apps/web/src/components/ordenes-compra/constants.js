// Constantes del modulo de Ordenes de Compra.
//
// R5: nombres auto-documentados (el nombre describe la entidad).

// Estados posibles de una OC, con su etiqueta visible en UI.
// El value "" representa "Todos" (sin filtro).
export const ESTADOS = [
  { value: "", label: "Todos" },
  { value: "borrador", label: "Borrador" },
  { value: "enviado_a_supervisor", label: "Enviado a supervisor" },
  { value: "aprobado", label: "Aprobado" },
  { value: "rechazado", label: "Rechazado" },
  { value: "comprado", label: "Comprado" },
];

// Badge (Tailwind classes) por estado.
export const ESTADO_BADGE = {
  borrador: "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
  enviado_a_supervisor: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  aprobado: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  rechazado: "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  comprado: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
};

// Pasos del timeline de estados (en orden).
export const ESTADO_TIMELINE = {
  borrador: ["Borrador"],
  enviado_a_supervisor: ["Borrador", "Enviado a supervisor"],
  aprobado: ["Borrador", "Enviado a supervisor", "Aprobado"],
  rechazado: ["Borrador", "Enviado a supervisor", "Rechazado"],
  comprado: ["Borrador", "Enviado a supervisor", "Aprobado", "Comprado"],
};
