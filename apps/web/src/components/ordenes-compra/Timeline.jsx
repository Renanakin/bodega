// Timeline visual de los pasos de estado de una OC.
import { ESTADO_TIMELINE } from "./constants";
import { formatFecha } from "./formatters";

export function Timeline({ estado, email_enviado_at, aprobado_at, comprado_at }) {
  const pasos = ESTADO_TIMELINE[estado] || ["Borrador"];
  const idxActual = pasos.length - 1;
  return (
    <ol className="space-y-1 text-sm">
      {pasos.map((p, i) => (
        <li key={p} className="flex items-center gap-2">
          <span
            className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
              i <= idxActual
                ? "bg-indigo-600 text-white"
                : "bg-slate-200 text-slate-500"
            }`}
            aria-hidden="true"
          >
            {i + 1}
          </span>
          <span className={i <= idxActual ? "font-medium text-slate-900" : "text-slate-500"}>
            {p}
          </span>
        </li>
      ))}
      <li className="ml-7 mt-2 space-y-0.5 text-xs text-slate-500">
        {email_enviado_at ? (
          <p>Email enviado: {formatFecha(email_enviado_at)}</p>
        ) : null}
        {aprobado_at ? <p>Aprobado: {formatFecha(aprobado_at)}</p> : null}
        {comprado_at ? <p>Comprado: {formatFecha(comprado_at)}</p> : null}
      </li>
    </ol>
  );
}
