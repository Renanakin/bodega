export const dashboardStats = [
  {
    title: "Stock valorizado",
    value: "$ 128.450.000",
    helper: "Actualizado hace 3 minutos",
    tone: "default",
  },
  {
    title: "Alertas criticas",
    value: "12",
    helper: "5 requieren compra inmediata",
    tone: "danger",
  },
  {
    title: "Transferencias activas",
    value: "9",
    helper: "3 en despacho, 6 en recepcion",
    tone: "warning",
  },
  {
    title: "Exactitud inventario",
    value: "98.7%",
    helper: "Ultimo conteo ciclico completado",
    tone: "success",
  },
];

export const activityItems = [
  {
    id: 1,
    title: "Transferencia TR-2026-0317-01 despachada",
    detail: "Central despacho 24 unidades a Sucursal Norte.",
    time: "Hace 12 min",
    tone: "success",
  },
  {
    id: 2,
    title: "Ajuste de inventario pendiente de aprobacion",
    detail: "Conteo ciclico detecto diferencia en rack Z-B-03.",
    time: "Hace 27 min",
    tone: "warning",
  },
  {
    id: 3,
    title: "Alerta critica de stock",
    detail: "Aceite Hidraulico 20L bajo el minimo en Sucursal Norte.",
    time: "Hace 41 min",
    tone: "danger",
  },
];

export const warehousePerformance = [
  { label: "Central", caption: "Despachos del dia", value: 82 },
  { label: "Norte", caption: "Pedidos preparados", value: 53 },
  { label: "Sur", caption: "Recepciones cerradas", value: 38 },
  { label: "Oriente", caption: "Conteos ciclicos", value: 29 },
];

export const kpiItems = [
  { label: "OTIF interno", value: "96.2%" },
  { label: "Tiempo picking", value: "11 min" },
  { label: "Recepcion promedio", value: "18 min" },
  { label: "Rotacion alta", value: "37 SKU" },
];

export const lowStockRows = [
  {
    id: 1,
    sku: "ACE-001",
    product: "Aceite Hidraulico 20L",
    warehouse: "Sucursal Norte",
    available: "4",
    minimum: "12",
    status: "Critico",
  },
  {
    id: 2,
    sku: "FIL-004",
    product: "Filtro Industrial 4P",
    warehouse: "Central",
    available: "8",
    minimum: "15",
    status: "Bajo",
  },
  {
    id: 3,
    sku: "TOR-220",
    product: "Tornillo Galvanizado 220",
    warehouse: "Sucursal Sur",
    available: "35",
    minimum: "40",
    status: "Bajo",
  },
];

export const transferRows = [
  {
    id: 1,
    code: "TR-2026-0317-01",
    from: "Central",
    to: "Sucursal Norte",
    status: "Despachada",
    eta: "Hoy 16:30",
  },
  {
    id: 2,
    code: "TR-2026-0317-02",
    from: "Central",
    to: "Sucursal Oriente",
    status: "Pendiente aprobacion",
    eta: "Sin programar",
  },
];

export const topProducts = [
  { id: 1, product: "Aceite Hidraulico 20L", units: "124", revenue: "$ 6.820.000" },
  { id: 2, product: "Filtro Industrial 4P", units: "92", revenue: "$ 4.170.000" },
  { id: 3, product: "Kit Mantenimiento M3", units: "81", revenue: "$ 7.215.000" },
];

export const lowRotation = [
  { id: 1, product: "Valvula Serie 7X", lastSale: "Hace 73 dias", action: "Revisar slotting" },
  { id: 2, product: "Correa XL 990", lastSale: "Hace 48 dias", action: "Reducir compra" },
  { id: 3, product: "Empaque PTFE 2.4", lastSale: "Hace 33 dias", action: "Mover a zona C" },
];

export const chatThreads = [
  {
    id: 1,
    channel: "Reposicion Norte",
    lastMessage: "Necesitamos reposicion de filtros antes de las 17:00.",
    owner: "Camila Vega",
    unread: 3,
  },
  {
    id: 2,
    channel: "Despacho Central",
    lastMessage: "Transferencia TR-2026-0317-01 lista para recepcion.",
    owner: "Cristobal Perez",
    unread: 0,
  },
  {
    id: 3,
    channel: "Compras urgentes",
    lastMessage: "Proveedor confirmo entrega parcial para manana.",
    owner: "Marisol Diaz",
    unread: 1,
  },
];

export const chatMessages = [
  {
    id: 1,
    author: "Camila Vega",
    role: "Jefa Sucursal Norte",
    text: "Necesitamos 8 filtros adicionales para cerrar el turno de manana.",
    time: "09:12",
  },
  {
    id: 2,
    author: "Bodega Central",
    role: "Sistema",
    text: "Hay disponibilidad interna. Se puede cubrir con transferencia parcial inmediata.",
    time: "09:14",
  },
  {
    id: 3,
    author: "Cristobal Perez",
    role: "Operador Central",
    text: "Estoy preparando el despacho. Confirmo salida en 20 minutos.",
    time: "09:18",
  },
];

export const slottingRows = [
  {
    id: 1,
    product: "Aceite Hidraulico 20L",
    currentSlot: "Z-C / R-08 / N-03",
    suggestedSlot: "Z-A / R-02 / N-01",
    reason: "Alta rotacion",
  },
  {
    id: 2,
    product: "Valvula Serie 7X",
    currentSlot: "Z-A / R-01 / N-01",
    suggestedSlot: "Z-C / R-10 / N-02",
    reason: "Baja rotacion",
  },
];

export const inventoryRows = [
  {
    id: 1,
    sku: "ACE-001",
    product: "Aceite Hidraulico 20L",
    warehouse: "Central",
    onHand: "72",
    reserved: "18",
    available: "54",
  },
  {
    id: 2,
    sku: "FIL-004",
    product: "Filtro Industrial 4P",
    warehouse: "Sucursal Norte",
    onHand: "24",
    reserved: "4",
    available: "20",
  },
];
