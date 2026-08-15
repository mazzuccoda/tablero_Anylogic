import { COLOR_ESTADO, Estado, ETIQUETA_ESTADO } from "@/lib/semaforo";

export function PildoraEstado({ estado }: { estado: Estado }) {
  const color = COLOR_ESTADO[estado];
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold"
      style={{ background: `${color}22`, color }}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
      {ETIQUETA_ESTADO[estado]}
    </span>
  );
}

/** Sparkline de hasta N puntos (huecos = sin dato, no se dibujan como cero). */
export function Sparkline({
  valores,
  estado,
}: {
  valores: (number | null)[];
  estado: Estado;
}) {
  const numeros = valores.filter((v): v is number => v !== null);
  if (numeros.length < 2) return null;

  const min = Math.min(...numeros);
  const max = Math.max(...numeros);
  const rango = max - min || 1;
  const n = valores.length;
  const puntos = valores.map((v, i) => ({
    x: 4 + (i * (116 - 4)) / (n - 1),
    y: v === null ? null : 30 - ((v - min) / rango) * 26,
  }));
  const validos = puntos.filter((p): p is { x: number; y: number } => p.y !== null);
  const color = COLOR_ESTADO[estado];
  const ultimo = validos[validos.length - 1];

  return (
    <svg className="mt-2 h-8 w-full" viewBox="0 0 120 34" role="img" aria-label="tendencia">
      <polyline
        points={validos.map((p) => `${p.x},${p.y}`).join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {ultimo ? (
        <circle cx={ultimo.x} cy={ultimo.y} r={4} fill={color} stroke="white" strokeWidth={2} />
      ) : null}
    </svg>
  );
}

export function TarjetaEstado({
  titulo,
  valor,
  detalle,
  estado,
  serie,
  delta,
}: {
  titulo: string;
  valor: string;
  detalle?: string;
  estado: Estado;
  serie?: (number | null)[];
  delta?: string;
}) {
  return (
    <div className="panel relative pr-4">
      <div className="absolute right-4 top-4">
        <PildoraEstado estado={estado} />
      </div>
      <div className="text-xs uppercase tracking-wide text-slate-500">{titulo}</div>
      <div className="mt-1 max-w-[75%] text-2xl font-semibold text-slate-900">{valor}</div>
      {detalle ? <div className="mt-1 text-xs text-slate-500">{detalle}</div> : null}
      {serie ? <Sparkline valores={serie} estado={estado} /> : null}
      {delta ? <div className="mt-1 text-xs font-medium text-slate-600">{delta}</div> : null}
    </div>
  );
}
