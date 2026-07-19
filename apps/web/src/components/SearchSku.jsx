import { useEffect, useRef, useState } from "react";

import { getJson } from "../lib/api.js";

/**
 * SearchSku: input con debounce 300ms que busca productos por SKU (Fase 2).
 *
 * Llama a GET /api/v1/products?sku=XXX y muestra los resultados en un
 * dropdown. Al seleccionar un item, se invoca ``onSelect(product)`` y
 * se limpia el input.
 *
 * Props:
 * - onSelect(product): callback al elegir un resultado.
 * - placeholder: texto del input.
 * - autoFocus: enfocar al montar.
 * - disabled: bloquear el input.
 * - minChars: minimo de caracteres para disparar la busqueda (default 2).
 * - debounceMs: delay del debounce (default 300ms).
 * - className: clases adicionales.
 */
const DEFAULT_DEBOUNCE_MS = 300;
const DEFAULT_MIN_CHARS = 2;

export function SearchSku({
  onSelect,
  placeholder = "Buscar por SKU o nombre...",
  autoFocus = true,
  disabled = false,
  minChars = DEFAULT_MIN_CHARS,
  debounceMs = DEFAULT_DEBOUNCE_MS,
  className = "",
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef(null);
  const abortRef = useRef(null);
  const containerRef = useRef(null);

  // Click outside cierra el dropdown
  useEffect(() => {
    function handleClick(event) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Debounce + fetch
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    const trimmed = query.trim();
    if (trimmed.length < minChars) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      // Aborta el request previo si sigue en vuelo
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      setError(null);
      try {
        const data = await getJson(
          `/products?sku=${encodeURIComponent(trimmed.toUpperCase())}`,
          { signal: controller.signal },
        );
        const list = Array.isArray(data) ? data : [];
        setResults(list);
        setOpen(list.length > 0);
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(err.message || "Error al buscar");
          setResults([]);
        }
      } finally {
        if (abortRef.current === controller) {
          setLoading(false);
        }
      }
    }, debounceMs);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, minChars, debounceMs]);

  const handleSelect = (product) => {
    setQuery("");
    setResults([]);
    setOpen(false);
    onSelect && onSelect(product);
  };

  const showDropdown = open && (results.length > 0 || loading || error);

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <input
        type="text"
        role="combobox"
        aria-label="Buscar SKU"
        aria-expanded={showDropdown}
        aria-autocomplete="list"
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => results.length > 0 && setOpen(true)}
        disabled={disabled}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm focus:border-bodega-accent focus:outline-none focus:ring-1 focus:ring-bodega-accent disabled:opacity-50"
      />

      {showDropdown && (
        <div className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-gray-200 bg-white shadow-lg">
          {loading && (
            <div className="px-3 py-2 text-sm text-bodega-muted">Buscando...</div>
          )}
          {error && (
            <div className="px-3 py-2 text-sm text-bodega-danger">
              {error}
            </div>
          )}
          {!loading && !error && results.length === 0 && (
            <div className="px-3 py-2 text-sm text-bodega-muted">
              Sin resultados para &quot;{query.trim()}&quot;
            </div>
          )}
          {!loading &&
            !error &&
            results.map((product) => (
              <button
                key={product.id}
                type="button"
                role="option"
                aria-selected="false"
                onClick={() => handleSelect(product)}
                className="block w-full cursor-pointer border-b border-gray-100 px-3 py-2 text-left text-sm last:border-0 hover:bg-bodega-accent/5 focus:bg-bodega-accent/10 focus:outline-none"
              >
                <div className="font-mono font-semibold text-bodega-ink">
                  {product.sku}
                </div>
                <div className="truncate text-xs text-bodega-muted">
                  {product.name}
                </div>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
