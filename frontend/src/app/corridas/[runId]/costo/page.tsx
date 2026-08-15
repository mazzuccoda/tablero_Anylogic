"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import {
  FilaDimension,
  Reconciliacion,
  ResumenCostos,
  Waterfall,
  traerPorDimension,
  traerReconciliacion,
  traerResumenCostos,
  traerWaterfall,
} from "@/lib/api";
import { numero, porcentaje, SIN_DATO, usd } from "@/lib/formato";

interface Datos {
  resumen: ResumenCostos;
  waterfall: Waterfall;
  reconciliacion: Reconciliacion;
  circuitos: FilaDimension[];
}

function baseDe(metrica: { base: { nombre: string; valor: number | null } }): string {
  return `base: ${metrica.base.nombre} = ${numero(metrica.base.valor)}`;
}

export default function PaginaCostoNivel2({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    const filtros = { tipo_contable: "CAJA" };
    Promise.all([
      traerResumenCostos(runId, filtros),
      traerWaterfall(runId, filtros),
      traerReconciliacion(runId, filtros),
      traerPorDimension(runId, "circuito", filtros),
    ])
      .then(([resumen, waterfall, reconciliacion, circuitos]) => {
        if (vigente) setDatos({ resumen, waterfall, reconciliacion, circuitos: circuitos.filas });
      })
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId]);

  const grafWaterfall = useMemo(() => {
    const pasos = datos?.waterfall.pasos ?? [];
    return {
      tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
      grid: { left: 8, right: 16, bottom: 60, top: 16, containLabel: true },
      xAxis: {
        type: "category" as const,
        data: pasos.map((p) => p.etapa),
        axisLabel: { rotate: 35, fontSize: 10 },
      },
      yAxis: { type: "value" as const, name: "USD" },
      series: [
        {
          name: "acumulado",
          type: "bar" as const,
          stack: "cascada",
          itemStyle: { color: "transparent" },
          emphasis: { itemStyle: { color: "transparent" } },
          tooltip: { show: false },
          data: pasos.map((p) => p.base),
        },
        {
          name: "etapa",
          type: "bar" as const,
          stack: "cascada",
          itemStyle: { color: "#3c4a8f" },
          data: pasos.map((p) => p.importe_usd ?? 0),
        },
      ],
    };
  }, [datos]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  const { resumen, waterfall, reconciliacion, circuitos } = datos;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Costo — {resumen.run_id}</h1>
          <p className="text-sm text-slate-500">nivel 2 · resumen temático, solo caja</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}`}>
            volver al resumen
          </Link>
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/costos`}>
            explorar costos (nivel 3)
          </Link>
        </div>
      </div>

      <Rejilla>
        <Kpi titulo="Costo total (caja)" valor={usd(resumen.importe_usd)} detalle={`${numero(resumen.eventos, 0)} cargos`} />
        <Kpi titulo="USD por tonelada" valor={usd(resumen.usd_por_tn.valor)} detalle={baseDe(resumen.usd_por_tn)} />
        <Kpi titulo="USD por contenedor" valor={usd(resumen.usd_por_contenedor.valor)} detalle={baseDe(resumen.usd_por_contenedor)} />
        <Kpi titulo="USD por pedido" valor={usd(resumen.usd_por_pedido.valor)} detalle={baseDe(resumen.usd_por_pedido)} />
      </Rejilla>

      <section className="panel">
        <h2 className="titulo-panel">Cascada por etapa logística</h2>
        <Grafico opcion={grafWaterfall} alto={320} />
        <p className="mt-2 text-xs text-slate-500">
          total {usd(waterfall.total_usd)}: es la suma de los pasos. El USD/tn de cada etapa tiene
          su propia base física — se ve completo en el explorador de nivel 3.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="panel">
          <h2 className="titulo-panel">Reconciliación</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th>dimensión</th>
                <th className="text-right">diferencia</th>
                <th>estado</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(reconciliacion.dimensiones).map(([dimension, fila]) => (
                <tr key={dimension}>
                  <td>{dimension}</td>
                  <td className="text-right">{usd(fila.diferencia)}</td>
                  <td
                    className={
                      fila.estado === "DESCUADRADA"
                        ? "text-critico"
                        : fila.estado === "PARCIAL"
                          ? "text-alerta"
                          : undefined
                    }
                  >
                    {fila.estado}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {reconciliacion.categorias_sin_clasificar.length > 0 ? (
            <p className="mt-2 text-xs text-alerta">
              categorías sin clasificar:{" "}
              {reconciliacion.categorias_sin_clasificar
                .map((c) => `${c.categoria || SIN_DATO} (${usd(c.importe_usd)})`)
                .join(", ")}
            </p>
          ) : null}
        </section>

        <section className="panel">
          <h2 className="titulo-panel">Circuito más caro</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th>circuito</th>
                <th className="text-right">importe</th>
                <th className="text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {circuitos.slice(0, 8).map((fila) => (
                <tr key={String(fila.circuito)}>
                  <td>{String(fila.circuito) || SIN_DATO}</td>
                  <td className="text-right">{usd(fila.importe_usd)}</td>
                  <td className="text-right">{porcentaje(fila.porcentaje)}</td>
                </tr>
              ))}
              {circuitos.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-4 text-center text-slate-500">
                    sin datos de circuito
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">
            ranking completo, filtros y drill-down hasta el evento en el explorador de nivel 3.
          </p>
        </section>
      </div>
    </div>
  );
}
