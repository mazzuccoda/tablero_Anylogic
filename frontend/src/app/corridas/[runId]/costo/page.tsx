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

interface ColumnaMatriz {
  importe: number;
  toneladas: number | null;
  porcentajeToneladas: number | null;
}

interface MatrizEstrategia {
  /** las N rutas nombradas mas pesadas — lo que muestra el panel en USD (sin cambios). */
  rutas: string[];
  /** rutas + "Resto de rutas" + "Sin ruta asignable": cubre el 100% del filtro, para que el
   * panel en USD/tn pueda ponderar contra el total real sin dejar nada afuera. */
  columnas: string[];
  celdas: Record<string, Record<string, number>>;
  totales: Record<string, ColumnaMatriz>;
}

const RESTO_DE_RUTAS = "Resto de rutas";
const SIN_RUTA_ASIGNABLE = "Sin ruta asignable";
const MAX_RUTAS_EN_MATRIZ = 6;

function baseDe(metrica: { base: { nombre: string; valor: number | null } }): string {
  return `base: ${metrica.base.nombre} = ${numero(metrica.base.valor)}`;
}

/** ADR-T06 (MOD v6): la matriz "estrategia por producto" — arcos en columnas, etapa en filas,
 * igual que la matriz del Excel de referencia. La columna ya no es el `circuito` declarado (un
 * tipo de consolidacion de 5 valores) sino la ruta fisica real, reconstruida por el backend
 * encadenando los sitios de ejecucion_arcos (`RUTA9→T4`, `DODERO→RUTA9→T4`...). Se filtra por
 * material, no por producto: es la granularidad que usa el Excel real (AEL/CDL/JCCL/JCL/PCL).
 *
 * Ademas de las N rutas mas pesadas (lo unico que muestra el panel en USD), agrupa todo lo que
 * queda afuera en "Resto de rutas" y "Sin ruta asignable" (ALMACENAMIENTO, FLETE_PRODUCTO — los
 * cargos que no llevan id_asignacion): sin esas dos columnas el panel en USD/tn no podria
 * ponderar contra el costo total de la corrida sin dejar plata afuera en silencio. */
async function matrizEstrategia(runId: string, material: string | null): Promise<MatrizEstrategia> {
  const filtros: Record<string, string> = { tipo_contable: "CAJA" };
  if (material) filtros.material = material;

  const [porRuta, porRutaYEtapa] = await Promise.all([
    traerPorRuta(runId, filtros),
    traerPorRutaYEtapa(runId, filtros),
  ]);

  const nombradas = porRuta.filas.filter((f) => f.ruta !== "SIN_RUTA");
  const top = nombradas.slice(0, MAX_RUTAS_EN_MATRIZ).map((f) => f.ruta);
  const resto = nombradas.slice(MAX_RUTAS_EN_MATRIZ).map((f) => f.ruta);
  const restoSet = new Set(resto);
  const sinRuta = porRuta.filas.find((f) => f.ruta === "SIN_RUTA") ?? null;

  const totales: MatrizEstrategia["totales"] = {};
  for (const fila of porRuta.filas) {
    if (!top.includes(fila.ruta)) continue;
    totales[fila.ruta] = {
      importe: fila.importe_usd ?? 0,
      toneladas: fila.toneladas,
      porcentajeToneladas: fila.porcentaje_toneladas,
    };
  }
  if (resto.length > 0) {
    const filasResto = nombradas.slice(MAX_RUTAS_EN_MATRIZ);
    totales[RESTO_DE_RUTAS] = {
      importe: filasResto.reduce((s, f) => s + (f.importe_usd ?? 0), 0),
      toneladas: filasResto.reduce((s, f) => s + (f.toneladas ?? 0), 0),
      porcentajeToneladas: filasResto.reduce((s, f) => s + (f.porcentaje_toneladas ?? 0), 0),
    };
  }
  if (sinRuta) {
    totales[SIN_RUTA_ASIGNABLE] = {
      importe: sinRuta.importe_usd ?? 0,
      toneladas: sinRuta.toneladas,
      porcentajeToneladas: sinRuta.porcentaje_toneladas,
    };
  }

  const columnas = [...top, ...(resto.length > 0 ? [RESTO_DE_RUTAS] : []), ...(sinRuta ? [SIN_RUTA_ASIGNABLE] : [])];

  const celdas: MatrizEstrategia["celdas"] = {};
  for (const celda of porRutaYEtapa.filas) {
    let columna: string | null = null;
    if (top.includes(celda.ruta)) columna = celda.ruta;
    else if (celda.ruta === "SIN_RUTA") columna = SIN_RUTA_ASIGNABLE;
    else if (restoSet.has(celda.ruta)) columna = RESTO_DE_RUTAS;
    if (!columna) continue;
    celdas[celda.etapa] ??= {};
    celdas[celda.etapa][columna] = (celdas[celda.etapa][columna] ?? 0) + (celda.importe_usd ?? 0);
  }

  return { rutas: top, columnas, celdas, totales };
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

      <MatrizUnitariaPanel matriz={matriz} etapasDelWaterfall={waterfall.pasos.map((p) => p.etapa)} resumen={resumen} />
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

function usdPorTn(importe: number, toneladas: number | null): number | null {
  if (!toneladas) return null;
  return importe / toneladas;
}

/** El mismo cruce etapa x ruta que el panel de arriba, pero en USD/tn en vez de USD — con dos
 * columnas que ese panel no muestra ("Resto de rutas" y "Sin ruta asignable") para que el
 * ponderado del pie no deje plata afuera: es la unica forma honesta de que coincida con el
 * costo total de la corrida. De paso, etapas que ningun arco nombrado factura directo —
 * ALMACENAMIENTO, el flete a depósito — aparecen porque viven en "Sin ruta asignable". */
function MatrizUnitariaPanel({
  matriz,
  etapasDelWaterfall,
  resumen,
}: {
  matriz: MatrizEstrategia | null;
  etapasDelWaterfall: string[];
  resumen: ResumenCostos;
}) {
  const columnas = matriz?.columnas ?? [];
  const etapas = (etapasDelWaterfall ?? []).filter((e) => matriz && e in matriz.celdas);

  const importeTotal = columnas.reduce((s, c) => s + (matriz?.totales[c]?.importe ?? 0), 0);
  const toneladasTotal = columnas.reduce((s, c) => s + (matriz?.totales[c]?.toneladas ?? 0), 0);
  const ponderado = usdPorTn(importeTotal, toneladasTotal);

  // "Sin ruta asignable" no tiene id_asignacion, asi que no tiene toneladas propias — son cargos
  // periodicos (ALMACENAMIENTO, flete a deposito), no ligados a un envio puntual. Repartirlos
  // sobre las toneladas totales de la red es la unica forma de que se vean en USD/tn en vez de
  // desaparecer en "sin dato": no es su tonelaje, es el tonelaje que sostiene ese costo comun.
  const toneladasDeLaColumna = (c: string): number | null =>
    c === SIN_RUTA_ASIGNABLE ? toneladasTotal || null : matriz?.totales[c]?.toneladas ?? null;

  return (
    <section className="panel">
      <h2 className="titulo-panel">Estrategia por producto — USD/tn por etapa</h2>
      <p className="mb-2 text-xs text-slate-500">
        el mismo cruce de arriba, en USD/tn: cada celda es el importe de esa etapa en esa columna
        dividido por las toneladas de esa columna. Con &quot;Resto de rutas&quot; y &quot;Sin ruta
        asignable&quot; (ALMACENAMIENTO, flete a depósito y demás cargos que no llevan
        <code>id_asignacion</code>, repartidos sobre las toneladas totales de la red porque no
        tienen envío propio) la tabla cubre el 100% del filtro, así que el ponderado del pie
        coincide con el costo total — nada queda afuera en silencio.
      </p>

      {!matriz ? (
        <p className="text-sm text-slate-500">cargando...</p>
      ) : columnas.length === 0 ? (
        <p className="text-sm text-slate-500">sin rutas físicas reconstruidas para este filtro</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead>
              <tr>
                <th>USD/tn</th>
                {columnas.map((c) => (
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
                  {columnas.map((c) => {
                    const importe = matriz.celdas[etapa]?.[c] ?? 0;
                    const valor = usdPorTn(importe, toneladasDeLaColumna(c));
                    return (
                      <td key={c} className="text-right">
                        {valor === null ? SIN_DATO : usd(valor)}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="font-semibold">
                <td>Total USD/tn</td>
                {columnas.map((c) => {
                  const col = matriz.totales[c];
                  const valor = col ? usdPorTn(col.importe, toneladasDeLaColumna(c)) : null;
                  return (
                    <td key={c} className="text-right">
                      {valor === null ? SIN_DATO : usd(valor)}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {matriz && columnas.length > 0 ? (
        <p className="mt-3 border-t border-slate-200 pt-2 text-xs text-slate-600">
          <strong>ponderado de esta tabla: {ponderado === null ? SIN_DATO : usd(ponderado)}</strong> ·{" "}
          {numero(toneladasTotal, 0)} tn asignadas (asignaciones_elegidas) — arriba, en la
          cabecera, USD por tonelada es {usd(resumen.usd_por_tn.valor)} sobre{" "}
          {baseDe(resumen.usd_por_tn)} (toneladas <em>entregadas</em>, no asignadas: por eso los
          dos números se acercan pero no tienen por qué ser idénticos).
        </p>
      ) : null}
    </section>
  );
}
