"use client";

import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import {
  Comparacion,
  Corrida,
  Dashboard,
  FilaEtapa,
  comparar,
  listarCorridas,
  traerDashboard,
  traerPorEtapa,
  traerRestricciones,
} from "@/lib/api";
import { fecha, numero, porcentaje, SIN_DATO, usd } from "@/lib/formato";

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

interface PasoCascada {
  etapa: string;
  a: number;
  b: number;
  diferencia: number;
}

/** Un paso por etapa, en el orden logistico que ya devuelve el backend (ORDEN_ETAPAS de
 * clasificacion.py) — no se reordena por magnitud, porque una cascada cuenta una secuencia. */
function pasosDeCascada(filasA: FilaEtapa[], filasB: FilaEtapa[]): PasoCascada[] {
  const valoresB = new Map(filasB.map((f) => [f.etapa, f.importe_usd ?? 0]));
  const etapas = new Map(filasA.map((f) => [f.etapa, f.importe_usd ?? 0]));
  for (const f of filasB) {
    if (!etapas.has(f.etapa)) etapas.set(f.etapa, 0);
  }
  return [...etapas.entries()].map(([etapa, a]) => {
    const b = valoresB.get(etapa) ?? 0;
    return { etapa, a, b, diferencia: b - a };
  });
}

interface ResumenAuditado {
  run_id: string;
  nivel_servicio: number | null;
  costo_usd_tn: number | null;
  sobrecosto_total_usd: number | null;
  uso_pico_pct: number | null;
}

/** Cuando las dos corridas estan auditadas pero ninguna trae kpis_por_corrida.csv, la comparacion
 * de barrido queda vacia — no por eso hay que dejar la pantalla sin nada: /dashboard/ y
 * /cost-explorer/constraints/ ya traen los mismos cuatro indicadores que nivel 1, por corrida. */
async function resumenAuditado(runId: string): Promise<ResumenAuditado> {
  const [dashboard, restricciones]: [Dashboard, Awaited<ReturnType<typeof traerRestricciones>> | null] =
    await Promise.all([traerDashboard(runId), traerRestricciones(runId).catch(() => null)]);
  const usos = (dashboard.capacidad?.por_recurso ?? [])
    .map((r) => r.uso_pico_pct)
    .filter((v): v is number => v !== null);
  return {
    run_id: runId,
    nivel_servicio: dashboard.servicio?.nivel_servicio ?? null,
    costo_usd_tn: dashboard.costos?.costo_usd_tn ?? null,
    sobrecosto_total_usd: restricciones?.sobrecosto_total_usd ?? null,
    uso_pico_pct: usos.length ? Math.max(...usos) : null,
  };
}

export default function PaginaComparar() {
  const [corridas, setCorridas] = useState<Corrida[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [resultado, setResultado] = useState<Comparacion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cascada, setCascada] = useState<PasoCascada[] | null>(null);
  const [errorCascada, setErrorCascada] = useState<string | null>(null);
  const [totales, setTotales] = useState<{ a: number | null; b: number | null } | null>(null);
  const [fallback, setFallback] = useState<{ a: ResumenAuditado; b: ResumenAuditado } | null>(null);

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
    setTotales(null);
    setFallback(null);
    let sinKpis = false;
    try {
      const r = await comparar(a, b);
      setResultado(r);
      sinKpis = r.sin_kpis;
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    const ambasAuditadas = corridaA?.tiene_drill_down && corridaB?.tiene_drill_down;
    if (ambasAuditadas) {
      try {
        const filtros = { tipo_contable: "CAJA" };
        const [porEtapaA, porEtapaB] = await Promise.all([
          traerPorEtapa(a, filtros),
          traerPorEtapa(b, filtros),
        ]);
        setCascada(pasosDeCascada(porEtapaA.filas, porEtapaB.filas));
        setTotales({ a: porEtapaA.importe_considerado, b: porEtapaB.importe_considerado });
      } catch (e) {
        setErrorCascada((e as Error).message);
      }
    }
    if (sinKpis && ambasAuditadas) {
      try {
        const [resA, resB] = await Promise.all([resumenAuditado(a), resumenAuditado(b)]);
        setFallback({ a: resA, b: resB });
      } catch {
        // si tambien falla el fallback, se queda solo el aviso de kpis_por_corrida vacio
      }
    }
  }

  const grafCascada = useMemo(() => {
    if (!cascada || totales === null) return null;
    const totalA = totales.a ?? 0;
    const totalB = totales.b ?? 0;
    let acumulado = totalA;
    const categorias = [`total ${a}`, ...cascada.map((p) => p.etapa), `total ${b}`];
    const base: (number | null)[] = [0];
    const incremento: { value: number; color: string }[] = [
      { value: totalA, color: "#3c4a8f" },
    ];
    for (const paso of cascada) {
      const antes = acumulado;
      acumulado += paso.diferencia;
      base.push(Math.min(antes, acumulado));
      incremento.push({
        value: Math.abs(paso.diferencia),
        color: paso.diferencia > 0 ? "#b91c1c" : paso.diferencia < 0 ? "#15803d" : "#94a3b8",
      });
    }
    base.push(0);
    incremento.push({ value: totalB, color: "#3c4a8f" });

    return {
      tooltip: {
        trigger: "axis" as const,
        axisPointer: { type: "shadow" as const },
        formatter: (params: unknown) => {
          const p = (params as { dataIndex: number }[])[0];
          const i = p.dataIndex;
          if (i === 0) return `total ${a}: ${usd(totalA)}`;
          if (i === categorias.length - 1) return `total ${b}: ${usd(totalB)}`;
          const paso = cascada[i - 1];
          return `${paso.etapa}<br/>${a}: ${usd(paso.a)}<br/>${b}: ${usd(paso.b)}<br/>diferencia: ${usd(paso.diferencia)}`;
        },
      },
      grid: { left: 8, right: 16, bottom: 70, top: 16, containLabel: true },
      xAxis: {
        type: "category" as const,
        data: categorias,
        axisLabel: { rotate: 40, fontSize: 10, interval: 0 },
      },
      yAxis: { type: "value" as const, name: "USD" },
      series: [
        {
          name: "base",
          type: "bar" as const,
          stack: "cascada",
          itemStyle: { color: "transparent" },
          emphasis: { itemStyle: { color: "transparent" } },
          tooltip: { show: false },
          data: base,
        },
        {
          name: "importe",
          type: "bar" as const,
          stack: "cascada",
          data: incremento.map((s) => ({ value: s.value, itemStyle: { color: s.color } })),
        },
      ],
    };
  }, [cascada, totales, a, b]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Comparar dos corridas</h1>
        <p className="text-sm text-slate-500">
          KPIs de kpis_por_corrida.csv cuando estan importados; si ambas corridas estan auditadas
          se suma una cascada de costo por etapa logistica y, si no hay KPIs de barrido, una
          comparacion de los mismos indicadores que el resumen de cada corrida.
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
              Ninguna de las dos corridas tiene KPIs de barrido importados (kpis_por_corrida.csv)
              {fallback ? ": abajo va la comparacion con los mismos indicadores del resumen de la corrida." : "."}
            </div>
          ) : null}

          {resultado.kpis.length > 0 ? (
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
          ) : null}

          {fallback ? (
            <table className="tabla">
              <thead>
                <tr>
                  <th>indicador</th>
                  <th className="text-right">{fallback.a.run_id}</th>
                  <th className="text-right">{fallback.b.run_id}</th>
                  <th className="text-right">diferencia</th>
                </tr>
              </thead>
              <tbody>
                <FilaFallback
                  titulo="Nivel de servicio"
                  a={fallback.a.nivel_servicio}
                  b={fallback.b.nivel_servicio}
                  formato={(v) => porcentaje(v, true)}
                />
                <FilaFallback
                  titulo="Costo USD/tn"
                  a={fallback.a.costo_usd_tn}
                  b={fallback.b.costo_usd_tn}
                  formato={usd}
                />
                <FilaFallback
                  titulo="Sobrecosto por restricciones"
                  a={fallback.a.sobrecosto_total_usd}
                  b={fallback.b.sobrecosto_total_usd}
                  formato={usd}
                />
                <FilaFallback
                  titulo="Ocupacion pico"
                  a={fallback.a.uso_pico_pct}
                  b={fallback.b.uso_pico_pct}
                  formato={(v) => porcentaje(v)}
                />
              </tbody>
            </table>
          ) : null}
        </section>
      ) : null}

      {errorCascada ? (
        <p className="text-xs text-alerta">no se pudo calcular la cascada por etapa: {errorCascada}</p>
      ) : null}

      {grafCascada ? (
        <section className="panel">
          <h2 className="titulo-panel">Cascada de costo por etapa logistica (solo caja)</h2>
          <Grafico opcion={grafCascada} alto={320} />
          <p className="mt-2 text-xs text-slate-500">
            de total {a} a total {b}, paso a paso por etapa: rojo suma, verde resta. Orden
            logistico, no por magnitud.
          </p>
        </section>
      ) : null}
    </div>
  );
}

function FilaFallback({
  titulo,
  a,
  b,
  formato,
}: {
  titulo: string;
  a: number | null;
  b: number | null;
  formato: (v: number | null) => string;
}) {
  const diferencia = a !== null && b !== null ? b - a : null;
  return (
    <tr>
      <td>{titulo}</td>
      <td className="text-right">{formato(a)}</td>
      <td className="text-right">{formato(b)}</td>
      <td className="text-right">{diferencia === null ? SIN_DATO : formato(diferencia)}</td>
    </tr>
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
