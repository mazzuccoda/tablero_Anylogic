import clsx from "clsx";

import type { Mensaje } from "@/lib/api";

export function Avisos({ mensajes }: { mensajes: Mensaje[] }) {
  if (mensajes.length === 0) return null;

  return (
    <ul className="space-y-1 text-sm">
      {mensajes.map((mensaje, indice) => (
        <li
          key={indice}
          className={clsx("rounded border px-3 py-2", {
            "border-red-200 bg-red-50 text-critico": mensaje.nivel === "ERROR",
            "border-amber-200 bg-amber-50 text-alerta": mensaje.nivel === "ADVERTENCIA",
            "border-borde bg-slate-50 text-slate-600": mensaje.nivel === "INFO",
          })}
        >
          <span className="font-medium">{mensaje.nivel}</span> — {mensaje.texto}
        </li>
      ))}
    </ul>
  );
}
