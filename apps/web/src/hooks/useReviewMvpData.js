import { useEffect, useState } from "react";

import { getJson, postJson } from "../lib/api";

const demoWarehouses = [
  { code: "CENTRAL", name: "Bodega Central", warehouse_type: "principal" },
  { code: "NORTE", name: "Sucursal Norte", warehouse_type: "auxiliar" },
];

const demoProducts = [
  { sku: "ACE-001", name: "Aceite Hidraulico 20L", unit: "unidad" },
  { sku: "FIL-004", name: "Filtro Industrial 4P", unit: "unidad" },
  { sku: "KIT-010", name: "Kit Mantenimiento M3", unit: "kit" },
];

export function useReviewMvpData() {
  const [state, setState] = useState({
    summary: null,
    warehouses: [],
    products: [],
    stock: [],
    movements: [],
    transfers: [],
    loading: true,
    error: "",
  });

  const refresh = async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));

    try {
      // C1.2: /transfers retorna 410 Gone (ADR-0003). Lo manejamos por
      // separado para que el resto de la página siga funcionando aunque
      // el backend ya no exponga el endpoint.
      const [summary, warehouses, products, stock, movements] = await Promise.all([
        getJson("/inventory/summary"),
        getJson("/warehouses"),
        getJson("/products"),
        getJson("/inventory/stock"),
        getJson("/inventory/movements"),
      ]);

      let transfers: unknown[] = [];
      try {
        transfers = await getJson("/transfers");
      } catch (transfersError: unknown) {
        // 410 Gone o cualquier error del módulo deprecado: silenciar
        // y devolver array vacío para que la UI no rompa.
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          console.warn("useReviewMvpData: /transfers no disponible (deprecado)", transfersError);
        }
      }

      setState({
        summary,
        warehouses,
        products,
        stock,
        movements,
        transfers,
        loading: false,
        error: "",
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : "No se pudo cargar el MVP.",
      }));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const seedDemoData = async () => {
    const warehouses = [...state.warehouses];
    const products = [...state.products];

    for (const demoWarehouse of demoWarehouses) {
      const existing = warehouses.find((item) => item.code === demoWarehouse.code);
      if (!existing) {
        warehouses.push(await postJson("/warehouses", demoWarehouse));
      }
    }

    for (const demoProduct of demoProducts) {
      const existing = products.find((item) => item.sku === demoProduct.sku);
      if (!existing) {
        products.push(await postJson("/products", demoProduct));
      }
    }

    if (!state.movements.length && !state.transfers.length) {
      const byCode = Object.fromEntries(warehouses.map((item) => [item.code, item]));
      const bySku = Object.fromEntries(products.map((item) => [item.sku, item]));

      await Promise.all([
        postJson("/inventory/movements", {
          warehouse_id: byCode.CENTRAL.id,
          product_id: bySku["ACE-001"].id,
          movement_type: "in",
          quantity: 72,
          reference_type: "demo",
          reference_id: "seed-001",
          notes: "Carga inicial para revision del MVP",
        }),
        postJson("/inventory/movements", {
          warehouse_id: byCode.CENTRAL.id,
          product_id: bySku["FIL-004"].id,
          movement_type: "in",
          quantity: 24,
          reference_type: "demo",
          reference_id: "seed-002",
          notes: "Ingreso inicial",
        }),
        postJson("/inventory/movements", {
          warehouse_id: byCode.CENTRAL.id,
          product_id: bySku["FIL-004"].id,
          movement_type: "in",
          quantity: 9,
          reference_type: "demo",
          reference_id: "seed-003",
          notes: "Stock adicional para transferir entre bodegas",
        }),
        postJson("/inventory/movements", {
          warehouse_id: byCode.CENTRAL.id,
          product_id: bySku["KIT-010"].id,
          movement_type: "adjustment_in",
          quantity: 11,
          reference_type: "demo",
          reference_id: "seed-005",
          notes: "Regularizacion de conteo",
        }),
      ]);
      // NOTA: la demo NO crea transfers/solicitudes automaticamente.
      // Las transferencias (1 producto) fueron reemplazadas por solicitudes_recarga
      // (N productos) segun ADR-0003. Probalas manualmente desde la pantalla
      // "Solicitudes" para ver el flujo end-to-end (crear -> aprobar -> despachar -> recibir).
    }

    await refresh();
  };

  return {
    ...state,
    refresh,
    seedDemoData,
  };
}
