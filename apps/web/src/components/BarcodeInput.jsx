import { useEffect, useRef, useState } from "react";

/**
 * BarcodeInput: input optimizado para lectores de codigo de barras (Fase 2).
 *
 * Comportamiento:
 * - Detecta `onKeyDown` (no `onChange`) para acumular el buffer del scanner.
 * - Reset del buffer si hay pausa > 100ms entre caracteres (tipico del
 *   ritmo de un scanner vs tipeo humano).
 * - `onScan(value)` se invoca al presionar Enter cuando el buffer tiene
 *   >= 6 caracteres (minimo razonable para un EAN-13 / Code-128 corto).
 * - Accesible: `aria-label`, `role="searchbox"`, `inputMode="numeric"`.
 *
 * Props:
 * - onScan(value: string): callback al detectar un barcode.
 * - placeholder: texto del input.
 * - autoFocus: enfocar al montar (default true).
 * - disabled: bloquear el input.
 * - minLength: longitud minima del buffer para disparar onScan (default 6).
 * - className: clases Tailwind adicionales.
 *
 * Uso:
 *   <BarcodeInput
 *     onScan={(bc) => handleScan(bc)}
 *     placeholder="Escanea codigo..."
 *     autoFocus
 *   />
 */
const DEFAULT_MIN_LENGTH = 6;
const THROTTLE_MS = 100;

export function BarcodeInput({
  onScan,
  autoFocus = true,
  disabled = false,
  placeholder = "Escanea codigo de barras...",
  minLength = DEFAULT_MIN_LENGTH,
  className = "",
  ariaLabel = "Escaner de codigo de barras",
}) {
  const bufferRef = useRef("");
  const lastKeyAtRef = useRef(0);
  const inputRef = useRef(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    if (autoFocus && inputRef.current && !disabled) {
      inputRef.current.focus();
    }
  }, [autoFocus, disabled]);

  const onKeyDown = (event) => {
    const now = performance.now();
    if (now - lastKeyAtRef.current > THROTTLE_MS) {
      bufferRef.current = ""; // Reset si hay pausa humana
    }
    lastKeyAtRef.current = now;

    if (event.key === "Enter") {
      event.preventDefault();
      const buffer = bufferRef.current.trim();
      if (buffer.length >= minLength) {
        onScan(buffer);
        bufferRef.current = "";
        setValue("");
        return;
      }
      // Fallback: usar el value del input si el scanner no inyecta onKeyDown
      // (e.g. paste manual). Tambien respeta minLength.
      const typed = (value || "").trim();
      if (typed.length >= minLength) {
        onScan(typed);
        setValue("");
      }
      return;
    }

    // Acumula solo caracteres utiles para un barcode (alfanum + separadores).
    if (/^[A-Za-z0-9\-._]$/.test(event.key)) {
      bufferRef.current += event.key;
    }
  };

  return (
    <input
      ref={inputRef}
      type="text"
      role="searchbox"
      inputMode="numeric"
      aria-label={ariaLabel}
      aria-disabled={disabled}
      autoComplete="off"
      spellCheck={false}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={onKeyDown}
      disabled={disabled}
      placeholder={placeholder}
      className={`w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm focus:border-bodega-accent focus:outline-none focus:ring-1 focus:ring-bodega-accent disabled:opacity-50 ${className}`}
    />
  );
}
