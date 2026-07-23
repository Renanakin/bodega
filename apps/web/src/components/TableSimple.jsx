import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Tabla simple.
 *
 * Soporta highlight de un item via query param ``?highlight=<id>``:
 * - La fila cuyo ``row.id`` coincida recibe la clase ``row-highlight``.
 * - Se hace scroll automatico a la fila al montar (cuando aplica).
 * - El highlight se quita automaticamente despues de 2.5s para no
 *   contaminar la vista si el usuario navega manualmente luego.
 */
export function TableSimple({ columns, rows }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const highlightId = searchParams.get("highlight");
  const tableRef = useRef(null);
  const highlightedRef = useRef(null);
  const clearTimerRef = useRef(null);

  useEffect(() => {
    if (!highlightId) return;
    // Scroll al item highlighted cuando existe
    const el = highlightedRef.current;
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    // Limpiar el query param despues de un rato para no dejar la URL sucia
    clearTimerRef.current = setTimeout(() => {
      if (searchParams.get("highlight")) {
        const next = new URLSearchParams(searchParams);
        next.delete("highlight");
        setSearchParams(next, { replace: true });
      }
    }, 2500);
    return () => {
      if (clearTimerRef.current) {
        clearTimeout(clearTimerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightId]);

  return (
    <div className="table-wrap" ref={tableRef}>
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const isHighlighted = highlightId && row.id === highlightId;
            return (
              <tr
                key={row.id ?? index}
                ref={isHighlighted ? highlightedRef : null}
                className={isHighlighted ? "row-highlight" : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key}>
                    {typeof column.render === "function"
                      ? column.render(row[column.key], row)
                      : row[column.key]}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
