"use client";

import clsx from "clsx";
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
  traerPorRuta,
  traerPorRutaYEtapa,
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
  materiales: FilaDimension[];
}

interface MatrizEstrategia {
  rutas: string[];
  celdas: Record<string, Record<string, number>>;
  totales: Record<string, { importe: number; toneladas: number | null; porcentajeToneladas: number | null }>;
}

const MAX_RUTAS_EN_MATRIZ = 6;

function baseDe(metrica: { base: { nombre: string; valor: number | null } }): string {
  return `base: ${metrica.base.nombre} = ${numero(metrica.base.valor)}`;
}

/** ADR-T06 (MOD v6): la matriz "estrategia por producto" — arcos en columnas, etapa en filas,
 * igual que la matriz del Excel de referencia. La columna ya no es el `circuito` declarado (un
 * tipo de consolidacion de 5 valores) sino la ruta fisica real, reconstruida por el backend
 * encadenando los sitios de ejecucion_arcos (`RUTA9→T4`, `DODERO→RUTA9→T4`...). Se filtra por
 * material, no por producto: es la granularidad que usa el Excel real (AEL/CDL/JCCL/JCL/PCL). */
async function matrizEstrategia(runId: string, material: string | null): Promise<MatrizEstrategia> {
  const filtros: Record<string, string> = { tipo_contable: "CAJA" };
  if (material) filtros.material = material;

  const [porRuta, porRutaYEtapa] = await Promise.all([
    traerPorRuta(runId, filtros),
    traerPorRutaYEtapa(runId, filtros),
  ]);

  const top = porRuta.filas
    .filter((f) => f.ruta !== "SIN_RUTA")
    .slice(0, MAX_RUTAS_EN_MATRIZ)
    .map((f) => f.ruta);

  const totales: MatrizEstrategia["totales"] = {};
  for (const fila of porRuta.filas) {
    if (top.includes(fila.ruta)) {
      totales[fila.ruta] = {
        importe: fila.importe_usd ?? 0,
        toneladas: fila.toneladas,
        porcentajeToneladas: fila.porcentaje_toneladas,
      };
    }
  }

  const celdas: MatrizEstrategia["celdas"] = {};
  for (const celda of porRutaYEtapa.filas) {
    if (!top.includes(celda.ruta)) continue;
    celdas[celda.etapa] ??= {};
    celdas[celda.etapa][celda.ruta] = celda.importe_usd ?? 0;
  }

  return { rutas: top, celdas, totales };
}

export default function PaginaCostoNivel2({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [material, setMaterial] = useState<string | null>(null);
  const [matriz, setMatriz] = useState<MatrizEstrategia | null>(null);
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
      traerPorDimension(runId, "material", filtros),
    ])
      .then(([resumen, waterfall, reconciliacion, circuitos, productos, materiales]) => {
        if (!vigente) return;
        setDatos({
          resumen,
          waterfall,
          reconciliacion,
          circuitos: circuitos.filas,
          productos: productos.filas,
          materiales: materiales.filas,
        });
      })
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId]);

  useEffect(() => {
    let vigente = true;
    setErrorMatriz(null);
    matrizEstrategia(runId, material)
      .then((m) => vigente && setMatriz(m))
      .catch((e: Error) => vigente && setErrorMatriz(e.message));
    return () => {
      vigente = false;
    };
  }, [runId, material]);

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

  const { resumen, waterfall, reconciliacion, circuitos, productos, materiales } = datos;

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
        <p className="text-xs text-alerta">no se pudo calcular la matriz de estrategia: {errorMatriz}</p>
      ) : null}

      <MatrizEstrategiaPanel
        matriz={matriz}
        etapasDelWaterfall={waterfall.pasos.map((p) => p.etapa)}
        materiales={materiales}
        materialSeleccionado={material}
        onMaterial={setMaterial}
      />
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

function MatrizEstrategiaPanel({
  matriz,
  etapasDelWaterfall,
  materiales,
  materialSeleccionado,
  onMaterial,
}: {
  matriz: MatrizEstrategia | null;
  etapasDelWaterfall: string[];
  materiales: FilaDimension[];
  materialSeleccionado: string | null;
  onMaterial: (material: string | null) => void;
}) {
  const etapas = (etapasDelWaterfall ?? []).filter((e) => matriz && e in matriz.celdas);
  const rutas = matriz?.rutas ?? [];
  const promedio =
    rutas.reduce((s, r) => s + (matriz?.totales[r]?.importe ?? 0), 0) / (rutas.length || 1);

  return (
    <section className="panel">
      <h2 className="titulo-panel">Estrategia por producto — matriz por etapa</h2>
      <p className="mb-2 text-xs text-slate-500">
        arcos en columnas (ruta física real, no el tipo de circuito), etapa logística en filas —
        la versión tablero de la matriz &quot;Estrategia&quot;. El total se compara contra el
        promedio de estos mismos arcos (no hay una referencia declarada por el usuario en el
        esquema, así que no se inventa una).
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-slate-500">material:</span>
        <button
          type="button"
          className={clsx(
            "rounded-full border px-2.5 py-1 text-xs",
            materialSeleccionado === null
              ? "border-acento bg-acento/10 font-semibold text-acento"
              : "border-slate-300 text-slate-700 hover:border-slate-400",
          )}
          onClick={() => onMaterial(null)}
        >
          todos
        </button>
        {materiales.map((fila) => {
          const valor = String(fila.material);
          return (
            <button
              key={valor}
              type="button"
              className={clsx(
                "rounded-full border px-2.5 py-1 text-xs",
                materialSeleccionado === valor
                  ? "border-acento bg-acento/10 font-semibold text-acento"
                  : "border-slate-300 text-slate-700 hover:border-slate-400",
              )}
              onClick={() => onMaterial(valor)}
            >
              {valor || SIN_DATO}
            </button>
          );
        })}
      </div>

      {!matriz ? (
        <p className="text-sm text-slate-500">cargando...</p>
      ) : rutas.length === 0 ? (
        <p className="text-sm text-slate-500">sin rutas físicas reconstruidas para este filtro</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead>
              <tr>
                <th>USD</th>
                {rutas.map((r) => (
                  <th key={r} className="text-right">
                    {r}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {etapas.map((etapa) => (
                <tr key={etapa}>
                  <td>{etapa}</td>
                  {rutas.map((r) => (
                    <td key={r} className="text-right">
                      {usd(matriz.celdas[etapa]?.[r] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="font-semibold">
                <td>Total</td>
                {rutas.map((r) => (
                  <td key={r} className={`text-right ${claseCalor(matriz.totales[r]?.importe ?? 0, promedio)}`}>
                    {usd(matriz.totales[r]?.importe ?? 0)}
                  </td>
                ))}
              </tr>
              <tr>
                <td>Tn</td>
                {rutas.map((r) => (
                  <td key={r} className="text-right">
                    {numero(matriz.totales[r]?.toneladas, 0)}
                  </td>
                ))}
              </tr>
              <tr>
                <td>% estrategia</td>
                {rutas.map((r) => (
                  <td key={r} className="text-right">
                    {porcentaje(matriz.totales[r]?.porcentajeToneladas)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">
        ruta física reconstruida encadenando <code>ejecucion_arcos</code> (ADR-T06) — no el
        <code>circuito</code> declarado, que es un tipo de consolidación. Tn y % estrategia
        salen de <code>asignaciones_elegidas</code>.
      </p>
    </section>
  );
}
