import { useCallback, useState } from "react";

import { MultibodegaGrid } from "../components/MultibodegaGrid.jsx";
import { SearchSku } from "../components/SearchSku.jsx";
import { BarcodeInput } from "../components/BarcodeInput.jsx";
import { getJson, getErrorMessage } from "../lib/api.js";
import { useUi } from "../context/UiContext.jsx";

/**
 * MultibodegaGridPage (Fase 2 / spec §4.1).
 *
 * Vista 100% Tailwind. Combina:
 * - SearchSku: busqueda por SKU/nombre con debounce 300ms.
 * - BarcodeInput: scanner de codigo de barras (>= 6 chars).
 * - MultibodegaGrid: render de la distribucion multibodega.
 *
 * Endpoint: GET /api/v1/inventario/real/distribucion?sku=XXX
 *
 * Estados cubiertos (regla AGENTS web): loading, empty, error, success.
 */
export function MultibodegaGridPage() {
  const { pushToast } = useUi();
  const [distribucion, setDistribucion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastSku, setLastSku] = useState(null);

  const fetchDistribucion = useCallback(
    async (sku) => {
      const normalized = (sku || "").trim().toUpperCase();
      if (!normalized) return;
      setLastSku(normalized);
      setLoading(true);
      setError(null);
      try {
        const data = await getJson(
          `/inventario/real/distribucion?sku=${encodeURIComponent(normalized)}`,
        );
        setDistribucion(data);
        if (!data) {
          pushToast({
            tone: "warning",
            title: "Producto no encontrado",
            description: `No existe un producto con SKU ${normalized}`,
          });
        }
      } catch (err) {
        const message = getErrorMessage(err, "Error al consultar la grilla");
        setError(message);
        setDistribucion(null);
        pushToast({
          tone: "danger",
          title: "Error de consulta",
          description: message,
        });
      } finally {
        setLoading(false);
      }
    },
    [pushToast],
  );

  const handleProductSelected = (product) => {
    if (product && product.sku) {
      fetchDistribucion(product.sku);
    }
  };

  const handleBarcodeScanned = (value) => {
    // El barcode se trata como SKU para esta vista (es el caso de uso tipico).
    fetchDistribucion(value);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold text-bodega-ink">Grilla Multibodega</h1>
        <p className="text-sm text-bodega-muted">
          Distribución física de un producto en todas las bodegas.
          Busca por SKU/nombre o escanea un código de barras.
        </p>
      </header>

      <section
        aria-label="Búsqueda de producto"
        className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
      >
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label
              htmlFor="searchsku-input"
              className="mb-1 block text-xs font-medium text-bodega-muted"
            >
              Buscar por SKU o nombre
            </label>
            <SearchSku
              onSelect={handleProductSelected}
              autoFocus
              placeholder="Ej. ACE-001, Filtro de aire..."
            />
          </div>
          <div>
            <label
              htmlFor="barcode-input"
              className="mb-1 block text-xs font-medium text-bodega-muted"
            >
              Escanear código de barras
            </label>
            <BarcodeInput
              onScan={handleBarcodeScanned}
              placeholder="Escanea y presiona Enter..."
            />
          </div>
        </div>
      </section>

      <MultibodegaGrid
        distribucion={distribucion}
        loading={loading}
        error={error}
      />

      {lastSku && !loading && distribucion && (
        <p className="text-center text-xs text-bodega-muted">
          Última consulta:{" "}
          <span className="font-mono font-semibold">{lastSku}</span>
        </p>
      )}
    </div>
  );
}
