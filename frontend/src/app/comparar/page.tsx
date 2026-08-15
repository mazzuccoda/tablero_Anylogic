"use client";

import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import {
  Comparacion,
  Corrida,
  FilaEtapa,
  comparar,
  listarCorridas,
  traerPorEtapa,
} from "@/lib/api";
import { fecha, numero, SIN_DATO, usd } from "@/lib/formato";

function agruparPorEscenario(corridas: Corrida[]): Record<string, Corrida[]> {
  const grupos: Record<string, Corrida[]> = {};
  for (const c of corridas) {
    (grupos[c.escenario] ??= []).push(c);
  }
  for (const escenario of Object.keys(grupos)) {
    grupos[escenario].sort((a, b) => (a.replica ?? 0) - (b.replica ?? 0));
  }
  return grupos;
}

/** Un par "sugerido" por escenario: las dos corridas auditadas mas recientes de esa familia —
 * es la comparacion que casi siempre se quiere ver primero (la ultima corrida contra la anterior). */
function sugerenciasDe(porEscenario: Record<string, Corrida[]>): { escenario: string; a: Corrida; b: Corrida }[] {
  const sugerencias: { escenario: string; a: Corrida; b: Corrida }[] = [];
  for (const [escenario, corridas] of Object.entries(porEscenario)) {
    const auditadas = corridas.filter((c) => c.tiene_drill_down);
    if (auditadas.length >= 2) {
      sugerencias.push({ escenario, a: auditadas[auditadas.length - 2], b: auditadas[auditadas.length - 1] });
    }
  }
  return sugerencias;
}

interface DiffEtapa {
  etapa: string;
  a: number;
  b: number;
  diferencia: number;
}

function diffPorEtapa(filasA: FilaEtapa[], filasB: FilaEtapa[]): DiffEtapa[] {
  const porEtapa = new Map<string, DiffEtapa>();
  for (const f of filasA) {
    porEtapa.set(f.etapa, { etapa: f.etapa, a: f.importe_usd ?? 0, b: 0, diferencia: 0 });
  }
  for (const f of filasB) {
    const existente = porEtapa.get(f.etapa) ?? { etapa: f.etapa, a: 0, b: 0, diferencia: 0 };
    existente.b = f.importe_usd ?? 0;
    porEtapa.set(f.etapa, existente);
  }
  const filas = [...porEtapa.values()].map((f) => ({ ...f, diferencia: f.b - f.a }));
  filas.sort((x, y) => Math.abs(y.diferencia) - Math.abs(x.diferencia));
  return filas;
}

export default function PaginaComparar() {
  const [corridas, setCorridas] = useState<Corrida[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [resultado, setResultado] = useState<Comparacion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cascada, setCascada] = useState<DiffEtapa[] | null>(null);
  const [errorCascada, setErrorCascada] = useState<string | null>(null);

  useEffect(() => {
    listarCorridas()
      .then((lista) => {
        setCorridas(lista);
        if (lista[0]) setA(lista[0].run_id);
        if (lista[1]) setB(lista[1].run_id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const porEscenario = useMemo(() => agruparPorEscenario(corridas), [corridas]);
  const sugerencias = useMemo(() => sugerenciasDe(porEscenario), [porEscenario]);
  const corridaA = corridas.find((c) => c.run_id === a) ?? null;
  const corridaB = corridas.find((c) => c.run_id === b) ?? null;

  async function ejecutar() {
    if (!a || !b) return;
    setError(null);
    setResultado(null);
    setCascada(null);
    setErrorCascada(null);
    try {
      setResultado(await comparar(a, b));
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    if (corridaA?.tiene_drill_down && corridaB?.tiene_drill_down) {
      try {
        const filtros = { tipo_contable: "CAJA" };
        const [porEtapaA, porEtapaB] = await Promise.all([
          traerPorEtapa(a, filtros),
          traerPorEtapa(b, filtros),
        ]);
        setCascada(diffPorEtapa(porEtapaA.filas, porEtapaB.filas));
      } catch (e) {
        setErrorCascada((e as Error).message);
      }
    }
  }

  const grafCascada = useMemo(() => {
    const filas = (cascada ?? []).slice(0, 12);
    return {
      tooltip: {
        trigger: "axis" as const,
        axisPointer: { type: "shadow" as const },
        formatter: (params: unknown) => {
          const p = (params as { name: string; value: number }[])[0];
          const fila = filas.find((f) => f.etapa === p.name);
          if (!fila) return p.name;
          return `${p.name}<br/>${a}: ${usd(fila.a)}<br/>${b}: ${usd(fila.b)}<br/>diferencia: ${usd(fila.diferencia)}`;
        },
      },
      grid: { left: 8, right: 16, bottom: 8, top: 16, containLabel: true },
      xAxis: { type: "value" as const, name: "USD (B − A)" },
      yAxis: { type: "category" as const, data: filas.map((f) => f.etapa).reverse() },
      series: [
        {
          type: "bar" as const,
          data: filas
            .map((f) => ({
              value: f.diferencia,
              itemStyle: { color: f.diferencia > 0 ? "#b91c1c" : f.diferencia < 0 ? "#15803d" : "#94a3b8" },
            }))
            .reverse(),
        },
      ],
    };
  }, [cascada, a, b]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Comparar dos corridas</h1>
        <p className="text-sm text-slate-500">
          KPIs de kpis_por_corrida.csv para cualquier par; si ambas corridas estan auditadas, se
          suma una cascada de costo por etapa logistica.
        </p>
      </div>

      {sugerencias.length > 0 ? (
        <section className="panel space-y-2">
          <h2 className="titulo-panel">sugeridas</h2>
          <div className="flex flex-wrap gap-2">
            {sugerencias.map((s) => (
              <button
                key={s.escenario}
                type="button"
                className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:border-acento hover:text-acento"
                onClick={() => {
                  setA(s.a.run_id);
                  setB(s.b.run_id);
                }}
              >
                {s.escenario}: {s.a.run_id} → {s.b.run_id}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PickerCorrida titulo="corrida A" porEscenario={porEscenario} seleccionada={a} alElegir={setA} />
        <PickerCorrida titulo="corrida B" porEscenario={porEscenario} seleccionada={b} alElegir={setB} />
      </div>

      <div className="flex items-center gap-3">
        <button className="boton-primario" disabled={!a || !b} onClick={ejecutar}>
          comparar
        </button>
        {corridaA && corridaB ? (
          <span className="text-xs text-slate-500">
            {corridaA.run_id} ({fecha(corridaA.fecha_inicio_campania)}) vs {corridaB.run_id} (
            {fecha(corridaB.fecha_inicio_campania)})
          </span>
        ) : null}
      </div>

      {error ? <p className="text-critico">{error}</p> : null}

      {resultado ? (
        <section className="panel space-y-3">
          <h2 className="titulo-panel">
            {resultado.a.run_id} vs {resultado.b.run_id}
          </h2>

          {resultado.sin_kpis ? (
            <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-alerta">
              Alguna de las dos corridas no tiene KPIs de barrido importados: la comparacion se
              hace sobre kpis_por_corrida.csv.
            </div>
          ) : null}

          <table className="tabla">
            <thead>
              <tr>
                <th>kpi</th>
                <th className="text-right">{resultado.a.run_id}</th>
                <th className="text-right">{resultado.b.run_id}</th>
                <th className="text-right">diferencia</th>
                <th className="text-right">variacion</th>
              </tr>
            </thead>
            <tbody>
              {resultado.kpis.map((fila) => (
                <tr key={fila.kpi}>
                  <td>{fila.kpi}</td>
                  <td className="text-right">{numero(fila.a, 4)}</td>
                  <td className="text-right">{numero(fila.b, 4)}</td>
                  <td className="text-right">{numero(fila.diferencia, 4)}</td>
                  <td className="text-right">
                    {fila.variacion_pct === null ? SIN_DATO : `${numero(fila.variacion_pct)} %`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {errorCascada ? (
        <p className="text-xs text-alerta">no se pudo calcular la cascada por etapa: {errorCascada}</p>
      ) : null}

      {cascada && cascada.length > 0 ? (
        <section className="panel">
          <h2 className="titulo-panel">Diferencia de costo por etapa logistica (solo caja)</h2>
          <Grafico opcion={grafCascada} alto={Math.max(240, cascada.length * 26)} />
          <p className="mt-2 text-xs text-slate-500">
            rojo: {b} costo mas que {a} en esa etapa · verde: {b} costo menos que {a}.
          </p>
        </section>
      ) : null}
    </div>
  );
}

function PickerCorrida({
  titulo,
  porEscenario,
  seleccionada,
  alElegir,
}: {
  titulo: string;
  porEscenario: Record<string, Corrida[]>;
  seleccionada: string;
  alElegir: (runId: string) => void;
}) {
  return (
    <section className="panel space-y-3">
      <h2 className="titulo-panel">{titulo}</h2>
      <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
        {Object.entries(porEscenario).map(([escenario, corridas]) => (
          <div key={escenario}>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{escenario}</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {corridas.map((c) => (
                <button
                  key={c.run_id}
                  type="button"
                  title={`${c.tipo === "AUDITORIA" ? "auditada" : "barrido"} · ${fecha(c.fecha_inicio_campania)}`}
                  className={clsx(
                    "rounded-full border px-2.5 py-1 text-xs",
                    seleccionada === c.run_id
                      ? "border-acento bg-acento/10 font-semibold text-acento"
                      : "border-slate-300 text-slate-700 hover:border-slate-400",
                    !c.tiene_drill_down && "opacity-70",
                  )}
                  onClick={() => alElegir(c.run_id)}
                >
                  {c.run_id}
                  {!c.tiene_drill_down ? " ·barrido" : ""}
                </button>
              ))}
            </div>
          </div>
        ))}
        {Object.keys(porEscenario).length === 0 ? (
          <p className="text-sm text-slate-500">no hay corridas cargadas todavia</p>
        ) : null}
      </div>
    </section>
  );
}
