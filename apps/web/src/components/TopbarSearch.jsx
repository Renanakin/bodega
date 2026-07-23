import { useEffect, useMemo, useRef, useState } from "react";

import { useNavigate } from "react-router-dom";

import { getErrorMessage, getJson } from "../lib/api";

/**
 * Busqueda global del topbar con dropdown de coincidencias.
 *
 * Cubre 3 tipos de entidades:
 * - Producto (sku / name)
 * - Solicitud de transferencia (codigo SOL-...)
 * - Bodega (code / name)
 *
 * Comportamiento:
 * - Debounce 200 ms para no saturar la API al teclear rapido.
 * - Top 8 resultados agrupados por tipo.
 * - Si no hay coincidencias: dropdown con estado vacio "No se encontraron
 *   coincidencias para '<query>'".
 * - Click en un resultado navega a la lista correspondiente y agrega
 *   ?highlight=<id> para que la pagina de destino resalte el item.
 * - ESC o click fuera cierra el dropdown.
 * - Si la query esta vacia, no se hace request y el dropdown se cierra.
 *
 * Las paginas de lista (/products, /warehouses, /solicitudes) leen
 * ``useSearchParams().get('highlight')`` y aplican un highlight visual
 * al item con ese id (ver componente ``TableSimple`` + CSS
 * ``.row-highlight``).
 */
const ENDPOINT_BY_TYPE = {
  producto: "/products",
  solicitud: "/solicitudes",
  bodega: "/warehouses",
};

const TYPE_LABEL = {
  producto: "Productos",
  solicitud: "Solicitudes",
  bodega: "Bodegas",
};

const TYPE_TO_PATH = {
  producto: "/products",
  solicitud: "/solicitudes",
  bodega: "/warehouses",
};

const TYPE_LIMIT = 4;
const DEBOUNCE_MS = 200;

function buildIndex(products, solicitudes, warehouses) {
  const idx = [];
  for (const p of products || []) {
    idx.push({
      type: "producto",
      id: p.id,
      title: p.sku,
      subtitle: p.name,
    });
  }
  for (const s of solicitudes || []) {
    idx.push({
      type: "solicitud",
      id: s.id,
      title: s.codigo,
      subtitle: `${s.bodega_origen_codigo || ""} -> ${s.bodega_destino_codigo || ""} (${s.estado || ""})`.trim(),
    });
  }
  for (const w of warehouses || []) {
    idx.push({
      type: "bodega",
      id: w.id,
      title: w.code,
      subtitle: `${w.name} (${w.warehouse_type || ""})`,
    });
  }
  return idx;
}

function scoreMatch(haystack, needle) {
  if (!haystack) return 0;
  const h = haystack.toLowerCase();
  const n = needle.toLowerCase();
  if (h === n) return 100;
  if (h.startsWith(n)) return 60;
  const idx = h.indexOf(n);
  if (idx >= 0) return 30 - Math.min(idx, 20);
  return 0;
}

export function TopbarSearch() {
  const navigate = useNavigate();
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  const lastQueryRef = useRef("");

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState([]);
  const [activeIndex, setActiveIndex] = useState(-1);

  // Cerrar al click fuera
  useEffect(() => {
    function handleClick(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Debounce + fetch
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setError("");
      setLoading(false);
      setActiveIndex(-1);
      return;
    }
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      lastQueryRef.current = q;
      try {
        const [products, solicitudes, warehouses] = await Promise.all([
          getJson(ENDPOINT_BY_TYPE.producto).catch(() => []),
          getJson(ENDPOINT_BY_TYPE.solicitud).catch(() => []),
          getJson(ENDPOINT_BY_TYPE.bodega).catch(() => []),
        ]);
        // Si la query cambio mientras esperabamos, descartamos este fetch.
        if (lastQueryRef.current !== q) {
          return;
        }
        const index = buildIndex(products, solicitudes, warehouses);
        const scored = index
          .map((item) => {
            const sTitle = scoreMatch(item.title, q);
            const sSub = scoreMatch(item.subtitle, q) * 0.6;
            return { ...item, _score: Math.max(sTitle, sSub) };
          })
          .filter((item) => item._score > 0)
          .sort((a, b) => b._score - a._score)
          .slice(0, 8);
        setResults(scored);
        setError("");
        setActiveIndex(scored.length ? 0 : -1);
      } catch (err) {
        setError(getErrorMessage(err));
        setResults([]);
      } finally {
        if (lastQueryRef.current === q) {
          setLoading(false);
        }
      }
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query]);

  const grouped = useMemo(() => {
    const groups = { producto: [], solicitud: [], bodega: [] };
    for (const r of results) {
      if (groups[r.type].length < TYPE_LIMIT) {
        groups[r.type].push(r);
      }
    }
    return groups;
  }, [results]);

  const handleSelect = (item) => {
    if (!item) return;
    setOpen(false);
    setQuery("");
    const path = TYPE_TO_PATH[item.type];
    navigate(`${path}?highlight=${encodeURIComponent(item.id)}`);
  };

  const handleKeyDown = (event) => {
    if (!open) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((idx) => (results.length ? (idx + 1) % results.length : -1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((idx) => (results.length ? (idx - 1 + results.length) % results.length : -1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = results[activeIndex];
      if (target) handleSelect(target);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const showDropdown = open && query.trim().length > 0;
  const noResults = showDropdown && !loading && !error && results.length === 0;

  return (
    <div className="topbar-search" ref={wrapperRef}>
      <input
        ref={inputRef}
        className="search-input"
        type="search"
        placeholder="Buscar producto, SKU o transferencia"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        autoComplete="off"
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls="topbar-search-listbox"
        aria-autocomplete="list"
      />
      {showDropdown ? (
        <div className="search-dropdown" id="topbar-search-listbox" role="listbox">
          {loading ? (
            <div className="search-dropdown-message">Buscando...</div>
          ) : error ? (
            <div className="search-dropdown-message search-dropdown-error">
              Error al buscar: {error}
            </div>
          ) : noResults ? (
            <div className="search-dropdown-empty">
              No se encontraron coincidencias para <strong>"{query.trim()}"</strong>
              <small>Prueba con SKU, codigo SOL-... o nombre de bodega.</small>
            </div>
          ) : (
            <>
              {Object.entries(grouped).map(([type, items]) => {
                if (!items.length) return null;
                return (
                  <div key={type} className="search-dropdown-group">
                    <div className="search-dropdown-group-title">{TYPE_LABEL[type]}</div>
                    {items.map((item) => {
                      const flatIndex = results.indexOf(item);
                      return (
                        <button
                          key={`${item.type}-${item.id}`}
                          type="button"
                          role="option"
                          aria-selected={flatIndex === activeIndex}
                          className={
                            flatIndex === activeIndex
                              ? "search-dropdown-item search-dropdown-item-active"
                              : "search-dropdown-item"
                          }
                          onMouseEnter={() => setActiveIndex(flatIndex)}
                          onClick={() => handleSelect(item)}
                        >
                          <span className="search-dropdown-item-title">{item.title}</span>
                          <span className="search-dropdown-item-subtitle">{item.subtitle}</span>
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
