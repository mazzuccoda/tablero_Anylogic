import clsx from "clsx";

export function Kpi({
  titulo,
  valor,
  detalle,
  tono = "normal",
}: {
  titulo: string;
  valor: string;
  detalle?: string;
  tono?: "normal" | "alerta" | "critico";
}) {
  return (
    <div className="panel">
      <div className="text-xs uppercase tracking-wide text-slate-500">{titulo}</div>
      <div
        className={clsx("mt-1 text-2xl font-semibold", {
          "text-slate-900": tono === "normal",
          "text-alerta": tono === "alerta",
          "text-critico": tono === "critico",
        })}
      >
        {valor}
      </div>
      {detalle ? <div className="mt-1 text-xs text-slate-500">{detalle}</div> : null}
    </div>
  );
}

export function Rejilla({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{children}</div>;
}
