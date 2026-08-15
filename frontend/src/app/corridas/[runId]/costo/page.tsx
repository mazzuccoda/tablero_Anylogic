"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import {
  FilaDimension,
  FilaEtapa,
  Reconciliacion,
  ResumenCostos,
  Waterfall,
  traerPorDimension,
  traerPorEtapa,
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
  productos: FilaDimension[];
}

interface MatrizCircuitos {
  circuitos: string[];
  celdas: Record<string, Record<string, number>>;
  totales: Record<string, number>;
}

const MAX_CIRCUITOS_EN_MATRIZ = 6;

function baseDe(metrica: { base: { nombre: string; valor: number | null } }): string {
  return `base: ${metrica.base.nombre} = ${numero(metrica.base.valor)}`;
}

/** Arcos en columnas, etapa logistica en filas — la version tablero de la matriz "por circuito"
 * del Excel de referencia. Cada columna es una llamada a by-stage/ filtrada por ese circuito (el
 * mismo endpoint que ya usa la cascada), no un endpoint nuevo. El orden de las etapas es el que ya
 * devuelve el backend (ORDEN_ETAPAS), no se reordena. */
async function matrizPorCircuito(runId: string, circuitos: FilaDimension[]): Promise<MatrizCircuitos> {
  const top = circuitos.slice(0, MAX_CIRCUITOS_EN_MATRIZ).map((f) => String(f.circuito));
  const porCircuito = await Promise.all(
    top.map((circuito) => traerPorEtapa(runId, { tipo_contable: "CAJA", circuito })),
  );
  const celdas: Record<string, Record<string, number>> = {};
  const totales: Record<string, number> = {};
  top.forEach((circuito, i) => {
    const filas: FilaEtapa[] = porCircuito[i].filas;
    totales[circuito] = porCircuito[i].importe_considerado ?? 0;
    for (const fila of filas) {
      celdas[fila.etapa] ??= {};
      celdas[fila.etapa][circuito] = fila.importe_usd ?? 0;
    }
  });
  return { circuitos: top, celdas, totales };
}

export default function PaginaCostoNivel2({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [matriz, setMatriz] = useState<MatrizCircuitos | null>(null);
  const [errorMatriz, setErrorMatriz] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    const filtros = { tipo_contable: "CAJA" };
    Promise.all([
      traerResumenCostos(runId, filtros),
      traerWaterfall(runId, filtros),
      traerReconciliacion(runId, filtros),
      traerPorDimension(runId, "circuito", filtros),
      traerPorDimension(runId, "producto", filtros),
    ])
      .then(([resumen, waterfall, reconciliacion, circuitos, productos]) => {
        if (!vigente) return;
        setDatos({
          resumen,
          waterfall,
          reconciliacion,
          circuitos: circuitos.filas,
          productos: productos.filas,
        });
        matrizPorCircuito(runId, circuitos.filas)
          .then((m) => vigente && setMatriz(m))
          .catch((e: Error) => vigente && setErrorMatriz(e.message));
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

  const { resumen, waterfall, reconciliacion, circuitos, productos } = datos;

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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="panel">
          <h2 className="titulo-panel">Apertura por material</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th>producto</th>
                <th className="text-right">importe</th>
                <th className="text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {productos.slice(0, 8).map((fila) => (
                <tr key={String(fila.producto)}>
                  <td>{String(fila.producto) || SIN_DATO}</td>
                  <td className="text-right">{usd(fila.importe_usd)}</td>
                  <td className="text-right">{porcentaje(fila.porcentaje)}</td>
                </tr>
              ))}
              {productos.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-4 text-center text-slate-500">
                    sin datos de producto
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">
            filtro por producto, ranking completo y drill-down en el explorador de nivel 3.
          </p>
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

      {errorMatriz ? (
        <p className="text-xs text-alerta">no se pudo calcular la matriz por circuito: {errorMatriz}</p>
      ) : null}

      {matriz && matriz.circuitos.length > 0 ? (
        <MatrizCircuitosPanel matriz={matriz} etapasDelWaterfall={waterfall.pasos.map((p) => p.etapa)} />
      ) : null}
    </div>
  );
}

function claseCalor(total: number, promedio: number): string {
  if (promedio <= 0) return "";
  const desvio = (total - promedio) / promedio;
  if (desvio <= -0.05) return "text-ok font-semibold";
  if (desvio >= 0.05) return "text-critico font-semibold";
  return "text-alerta font-semibold";
}

function MatrizCircuitosPanel({
  matriz,
  etapasDelWaterfall,
}: {
  matriz: MatrizCircuitos;
  etapasDelWaterfall: string[];
}) {
  const etapas = etapasDelWaterfall.filter((e) => e in matriz.celdas);
  const promedio =
    matriz.circuitos.reduce((s, c) => s + (matriz.totales[c] ?? 0), 0) / (matriz.circuitos.length || 1);

  return (
    <section className="panel">
      <h2 className="titulo-panel">Costo por circuito — matriz por etapa</h2>
      <p className="mb-2 text-xs text-slate-500">
        los {matriz.circuitos.length} circuitos más caros, componentes de costo en filas. El total
        se compara contra el promedio de estos mismos circuitos (no hay una referencia declarada
        por el usuario en el esquema, así que no se inventa una).
      </p>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr>
              <th>USD</th>
              {matriz.circuitos.map((c) => (
                <th key={c} className="text-right">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {etapas.map((etapa) => (
              <tr key={etapa}>
                <td>{etapa}</td>
                {matriz.circuitos.map((c) => (
                  <td key={c} className="text-right">
                    {usd(matriz.celdas[etapa]?.[c] ?? 0)}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="font-semibold">
              <td>Total</td>
              {matriz.circuitos.map((c) => (
                <td key={c} className={`text-right ${claseCalor(matriz.totales[c] ?? 0, promedio)}`}>
                  {usd(matriz.totales[c] ?? 0)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        cada columna es <code>by-stage</code> filtrado por ese circuito — el mismo endpoint que la
        cascada de arriba. No hay toneladas por circuito en el esquema, así que la matriz queda en
        USD, no USD/tn.
      </p>
    </section>
  );
}
