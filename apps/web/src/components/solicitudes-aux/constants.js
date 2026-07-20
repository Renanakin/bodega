// Constantes para la pagina de Solicitudes de Recarga.

export const ESTADOS = [
  { value: "", label: "Todos" },
  { value: "pending", label: "Pendiente" },
  { value: "approved", label: "Aprobada" },
  { value: "in_transit", label: "En transito" },
  { value: "partially_received", label: "Recepcion parcial" },
  { value: "received", label: "Recibida" },
  { value: "rejected", label: "Rechazada" },
  { value: "cancelled", label: "Cancelada" },
];

export const ETIQUETA_ESTADO = {
  pending: "Pendiente",
  approved: "Aprobada",
  in_transit: "En transito",
  partially_received: "Recepcion parcial",
  received: "Recibida",
  rejected: "Rechazada",
  cancelled: "Cancelada",
  partial: "Recepcion parcial",
};

export const COLOR_ESTADO = {
  pending: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  approved: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  in_transit: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  partially_received: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  partial: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  received: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  rejected: "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  cancelled: "bg-slate-200 text-slate-700 ring-1 ring-slate-300",
};

export const COLOR_PRIORIDAD = {
  alta: "text-rose-700 font-semibold",
  urgente: "text-rose-700 font-bold",
  normal: "text-slate-600",
};

export const PAGE_SIZE = 25;
