"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import {
  AlmacenajePorProducto,
  Cintas,
  Deposito,
  FlujoDeposito,
  RecorridoLote,
  StockDiario,
  TopLotes,
  traerAlmacenajePorProducto,
  traerCintas,
  traerDepositos,
  traerFlujoDeposito,
  traerRecorridoLote,
  traerStockDiario,
  traerTopLotes,
} from "@/lib/api";
import { numero, porcentaje, SIN_DATO, usd } from "@/lib/formato";

/** Paleta por producto: el mismo producto tiene que ser del mismo color en el sankey, en la tabla
 * y en la serie diaria; si no, comparar dos paneles obliga a leer la leyenda cada vez. */
const PALETA = ["#0f766e", "#b45309", "#1d4ed8", "#7e22ce", "#be123c", "#4d7c0f"];

function colorDe(producto: string, productos: string[]): string {
  const posicion = productos.indexOf(producto);
  return PALETA[(posicion < 0 ? 0 : posicion) % PALETA.length];
}

const ORDENES_LOTES = [
  { valor: "costo", titulo: "por costo" },
  { valor: "dias", titulo: "por dias" },
  { valor: "toneladas", titulo: "por toneladas" },
] as const;

interface Datos {
  cintas: Cintas;
  almacenaje: AlmacenajePorProducto;
  depositos: Deposito[];
  lotes: TopLotes;
}

export default function PaginaFlujo({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [orden, setOrden] = useState<string>("costo");
  const [error, setError] = useState<string | null>(null);
  const [deposito, setDeposito] = useState<string | null>(null);
  const [detalleDeposito, setDetalleDeposito] = useState<{
    flujo: FlujoDeposito;
    stock: StockDiario;
  } | null>(null);
  const [lote, setLote] = useState<RecorridoLote | null>(null);

  useEffect(() => {
    let vigente = true;
    setError(null);
    Promise.all([
      traerCintas(runId, {}),
      traerAlmacenajePorProducto(runId, {}),
      traerDepositos(runId),
      traerTopLotes(runId, { orden }),
    ])
      .then(([cintas, almacenaje, depositos, lotes]) => {
        if (!vigente) return;
        setDatos({ cintas, almacenaje, depositos: depositos.depositos, lotes });
        setDeposito((actual) => actual ?? almacenaje.depositos[0] ?? null);
      })
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId, orden]);

  useEffect(() => {
    if (!deposito) return;
    let vigente = true;
    Promise.all([traerFlujoDeposito(runId, deposito), traerStockDiario(runId, deposito)])
      .then(([flujo, stock]) => vigente && setDetalleDeposito({ flujo, stock }))
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId, deposito]);

  const productos = useMemo(
    () => (datos?.almacenaje.filas ?? []).map((fila) => fila.producto),
    [datos],
  );

  const grafSankey = useMemo(() => {
    const cintas = datos?.cintas.cintas ?? [];
    return {
      tooltip: { trigger: "item" as const, triggerOn: "mousemove|click" as const },
      series: [
        {
          type: "sankey" as const,
          emphasis: { focus: "adjacency" as const },
          nodeAlign: "left" as const,
          left: 8,
          right: 96,
          data: (datos?.cintas.nodos ?? []).map((nodo) => ({ name: nodo.id })),
          links: cintas.map((cinta) => ({
            source: cinta.origen,
            target: cinta.destino,
            value: cinta.toneladas,
            lineStyle: { color: colorDe(cinta.producto, productos), opacity: 0.45 },
            tooltip: {
              formatter: () =>
                `${cinta.origen} → ${cinta.destino}<br/>${cinta.producto}: ` +
                `${numero(cinta.toneladas)} tn en ${numero(cinta.arcos, 0)} arcos`,
            },
          })),
          label: { fontSize: 11 },
        },
      ],
    };
  }, [datos, productos]);

  const grafStock = useMemo(() => {
    const serie = detalleDeposito?.stock.serie_diaria ?? [];
    const dias = [...new Set(serie.map((fila) => fila.dia))].sort((a, b) => a - b);
    const nombres = detalleDeposito?.stock.productos ?? [];
    return {
      tooltip: { trigger: "axis" as const },
      legend: { bottom: 0, textStyle: { fontSize: 10 } },
      grid: { left: 8, right: 16, bottom: 34, top: 16, containLabel: true },
      xAxis: { type: "category" as const, data: dias, name: "dia" },
      yAxis: { type: "value" as const, name: "tn" },
      series: nombres.map((producto) => ({
        name: producto,
        type: "line" as const,
        showSymbol: false,
        areaStyle: { opacity: 0.15 },
        itemStyle: { color: colorDe(producto, productos) },
        data: dias.map(
          (dia) =>
            serie.find((fila) => fila.dia === dia && fila.producto === producto)
              ?.stock_fisico_tn ?? null,
        ),
      })),
    };
  }, [detalleDeposito, productos]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  const { cintas, almacenaje } = datos;
  const totalCaja =
    cintas.costo_etapas_usd + (cintas.almacenamiento_excluido_usd ?? 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Flujo fisico y almacenaje de {cintas.run_id}</h1>
          <p className="text-sm text-slate-500">
            toneladas de ejecucion_arcos, importes de costos_eventos ({cintas.tipo_contable})
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}`}>
            volver al dashboard
          </Link>
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/costos`}>
            explorar costos
          </Link>
        </div>
      </div>

      <Rejilla>
        <Kpi
          titulo="Costo de las etapas"
          valor={usd(cintas.costo_etapas_usd)}
          detalle="todo lo que no es almacenaje"
        />
        <Kpi
          titulo="Almacenaje"
          valor={usd(cintas.almacenamiento_excluido_usd)}
          detalle={`${numero(cintas.almacenamiento_eventos, 0)} cargos · no es un arco, va aparte`}
        />
        <Kpi titulo="Total CAJA" valor={usd(totalCaja)} detalle="etapas + almacenaje" />
        <Kpi
          titulo="Toneladas entregadas"
          valor={numero(cintas.toneladas_entregadas)}
          detalle="descarga en terminal"
        />
      </Rejilla>

      <section className="panel">
        <h2 className="titulo-panel">Como se movio el producto</h2>
        <p className="mb-2 text-xs text-slate-500">{cintas.base_cintas}</p>
        <Grafico opcion={grafSankey} alto={360} />
        {cintas.tipos_arco_no_dibujados.length > 0 ? (
          <details className="mt-2 text-xs text-slate-500">
            <summary className="cursor-pointer">
              {cintas.tipos_arco_no_dibujados.length} tipos de arco fuera del diagrama
            </summary>
            <ul className="mt-1 space-y-1">
              {cintas.tipos_arco_no_dibujados.map((fila) => (
                <li key={fila.tipo_arco}>
                  {fila.tipo_arco}: {numero(fila.toneladas)} tn en {numero(fila.arcos, 0)} arcos —{" "}
                  {fila.motivo}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Etapa fisica: toneladas y costo</h2>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead>
              <tr>
                <th>etapa</th>
                <th className="text-right">toneladas</th>
                <th className="text-right">arcos</th>
                <th className="text-right">costo</th>
                <th className="text-right">USD/tn</th>
                <th>categorias</th>
              </tr>
            </thead>
            <tbody>
              {cintas.etapas.map((etapa) => (
                <tr key={etapa.etapa}>
                  <td>{etapa.etapa}</td>
                  <td className="text-right">{numero(etapa.toneladas)}</td>
                  <td className="text-right">{numero(etapa.arcos, 0)}</td>
                  <td className="text-right">{usd(etapa.costo_usd)}</td>
                  <td className="text-right">{usd(etapa.usd_por_tn)}</td>
                  <td className="text-xs text-slate-500">
                    {etapa.categorias.join(", ") || etapa.tipos_arco.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          una etapa sin cargo propio (las esperas) muestra {SIN_DATO} y no cero; una etapa sin arco
          (THC, despachante) no tiene toneladas. {cintas.nota}.
        </p>
      </section>

      <PanelPorProducto almacenaje={almacenaje} productos={productos} />

      <section className="panel">
        <h2 className="titulo-panel">Almacenaje por deposito</h2>
        <div className="mb-3 flex flex-wrap gap-2">
          {datos.depositos.map((fila) => (
            <button
              key={fila.ubicacion}
              className="boton min-h-11"
              aria-pressed={deposito === fila.ubicacion}
              onClick={() => setDeposito(fila.ubicacion)}
              style={
                deposito === fila.ubicacion
                  ? { background: "#0f766e", color: "white", borderColor: "#0f766e" }
                  : undefined
              }
            >
              {fila.ubicacion}
              <span className="ml-2 text-xs opacity-70">{usd(fila.costo_almacenaje_usd)}</span>
            </button>
          ))}
        </div>
        {detalleDeposito ? (
          <PanelDeposito flujo={detalleDeposito.flujo} grafico={grafStock} />
        ) : (
          <p className="text-sm text-slate-500">elegir un deposito</p>
        )}
      </section>

      <section className="panel">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h2 className="titulo-panel mb-0">Lotes que mas costaron guardar</h2>
          {ORDENES_LOTES.map((opcion) => (
            <button
              key={opcion.valor}
              className="boton"
              aria-pressed={orden === opcion.valor}
              onClick={() => setOrden(opcion.valor)}
              style={
                orden === opcion.valor
                  ? { background: "#0f766e", color: "white", borderColor: "#0f766e" }
                  : undefined
              }
            >
              {opcion.titulo}
            </button>
          ))}
        </div>
        <p className="mb-2 text-xs text-slate-500">{datos.lotes.base_toneladas}</p>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead>
              <tr>
                <th>lote</th>
                <th>producto</th>
                <th>deposito</th>
                <th className="text-right">costo</th>
                <th className="text-right">dias</th>
                <th className="text-right">tn</th>
                <th className="text-right">USD/tn</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {datos.lotes.lotes.slice(0, 20).map((fila) => (
                <tr key={fila.id_lote}>
                  <td>{fila.id_lote || SIN_DATO}</td>
                  <td>{fila.producto || SIN_DATO}</td>
                  <td>{fila.sitio || SIN_DATO}</td>
                  <td className="text-right">{usd(fila.costo_almacenaje_usd)}</td>
                  <td className="text-right">{numero(fila.dias_con_cargo, 0)}</td>
                  <td className="text-right">{numero(fila.toneladas)}</td>
                  <td className="text-right">{usd(fila.usd_por_tn)}</td>
                  <td className="text-right">
                    <button
                      className="boton"
                      onClick={() =>
                        traerRecorridoLote(runId, fila.id_lote)
                          .then(setLote)
                          .catch((e: Error) => setError(e.message))
                      }
                    >
                      recorrido
                    </button>
                  </td>
                </tr>
              ))}
              {datos.lotes.lotes.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-slate-500">
                    la corrida no tiene cargos de almacenaje por lote
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {lote ? <PanelLote lote={lote} runId={runId} onCerrar={() => setLote(null)} /> : null}
    </div>
  );
}

function PanelPorProducto({
  almacenaje,
  productos,
}: {
  almacenaje: AlmacenajePorProducto;
  productos: string[];
}) {
  const descuadre = almacenaje.descuadre_contra_snapshot;
  return (
    <section className="panel">
      <h2 className="titulo-panel">Almacenaje por producto</h2>
      <p className="mb-3 text-xs text-slate-500">
        {almacenaje.base_sitios}. {almacenaje.base_dias}.
      </p>
      <div className="mb-3 space-y-2">
        {almacenaje.filas.map((fila) => (
          <div key={fila.producto} className="flex items-center gap-2">
            <span className="w-24 shrink-0 text-xs">{fila.producto}</span>
            <div className="h-3 flex-1 rounded bg-slate-100">
              <div
                className="h-3 rounded"
                style={{
                  width: `${(fila.porcentaje ?? 0) * 100}%`,
                  background: colorDe(fila.producto, productos),
                }}
              />
            </div>
            <span className="w-32 shrink-0 text-right text-xs">
              {usd(fila.costo_almacenaje_usd)}
            </span>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr>
              <th>producto</th>
              <th className="text-right">ingresos (tn)</th>
              <th className="text-right">stock prom. (tn)</th>
              <th className="text-right">egresos (tn)</th>
              <th className="text-right">dias prom.</th>
              <th className="text-right">costo</th>
              <th className="text-right">USD/tn ingresada</th>
              <th className="text-right">%</th>
            </tr>
          </thead>
          <tbody>
            {almacenaje.filas.map((fila) => (
              <tr key={fila.producto}>
                <td>{fila.producto}</td>
                <td className="text-right">{numero(fila.ingresos_tn)}</td>
                <td className="text-right">{numero(fila.stock_promedio_tn)}</td>
                <td className="text-right">{numero(fila.egresos_tn)}</td>
                <td className="text-right">{numero(fila.dias_promedio_deposito)}</td>
                <td className="text-right">{usd(fila.costo_almacenaje_usd)}</td>
                <td className="text-right">{usd(fila.usd_por_tn_ingresada)}</td>
                <td className="text-right">{porcentaje(fila.porcentaje, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {almacenaje.base_egresos}. Un producto que se guarda donde no se cobra almacenaje aparece
        con {SIN_DATO}, no con cero.
      </p>
      {descuadre.declarado_usd !== null ? (
        <p className="mt-1 text-xs text-alerta">
          snapshot_inventario declara {usd(descuadre.declarado_usd)} de almacenaje contra{" "}
          {usd(descuadre.contable_usd)} de costos_eventos ({usd(descuadre.diferencia_usd)} de
          diferencia): el tablero usa costos_eventos.
        </p>
      ) : null}
    </section>
  );
}

function Caja({ titulo, valor, detalle }: { titulo: string; valor: string; detalle?: string }) {
  return (
    <div className="rounded border border-borde bg-slate-50 px-3 py-2 text-center">
      <div className="text-xs uppercase tracking-wide text-slate-500">{titulo}</div>
      <div className="text-lg font-semibold">{valor}</div>
      {detalle ? <div className="text-xs text-slate-500">{detalle}</div> : null}
    </div>
  );
}

/** La flecha rota 90 grados en mobile: el flujo pasa de horizontal a vertical sin cambiar el DOM. */
function Flecha({ costo }: { costo: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-slate-400">
      <span className="rotate-90 text-xl leading-none sm:rotate-0">→</span>
      <span className="text-xs text-slate-500">{costo}</span>
    </div>
  );
}

function PanelDeposito({
  flujo,
  grafico,
}: {
  flujo: FlujoDeposito;
  grafico: Parameters<typeof Grafico>[0]["opcion"];
}) {
  const { costo, decision } = flujo;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr]">
        <Caja
          titulo="Ingresos"
          valor={`${numero(flujo.flujo.ingresos_tn)} tn`}
          detalle={`${numero(flujo.flujo.arcos_de_ingreso, 0)} arcos de entrada`}
        />
        <Flecha costo={usd(costo.costo_ingreso_usd)} />
        <Caja
          titulo="Stock"
          valor={`${numero(flujo.flujo.stock_promedio_tn)} tn`}
          detalle={`pico ${numero(flujo.flujo.stock_maximo_tn)} tn · ocupacion ${porcentaje(
            flujo.flujo.ocupacion_pico_pct,
          )} · ${numero(flujo.flujo.dias_promedio_deposito)} dias`}
        />
        <Flecha costo={usd(costo.costo_egreso_usd)} />
        <Caja
          titulo="Egresos"
          valor={`${numero(flujo.flujo.egresos_tn)} tn`}
          detalle={`${numero(flujo.flujo.arcos_de_egreso, 0)} arcos de salida`}
        />
      </div>
      <p className="text-xs text-slate-500">
        almacenaje {usd(costo.costo_almacenaje_usd)} · costo total del sitio{" "}
        {usd(costo.costo_total_usd)}. {flujo.flujo.base_egresos}.
      </p>

      <Grafico opcion={grafico} alto={260} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-semibold">Por que el modelo lo eligio (o no)</h3>
          <p className="text-xs text-slate-500">
            {numero(decision.evaluaciones, 0)} evaluaciones · elegida {numero(decision.elegida, 0)}{" "}
            veces · ranking promedio {numero(decision.orden_ranking_promedio)} ·{" "}
            {numero(decision.no_factible, 0)} no factibles ({numero(
              decision.mas_barata_no_factible,
              0,
            )}{" "}
            eran la mas barata)
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="tabla">
              <thead>
                <tr>
                  <th>motivo de descarte</th>
                  <th className="text-right">veces</th>
                </tr>
              </thead>
              <tbody>
                {decision.motivos_de_descarte.slice(0, 8).map((fila) => (
                  <tr key={fila.codigo_motivo}>
                    <td>{fila.codigo_motivo}</td>
                    <td className="text-right">{numero(fila.veces, 0)}</td>
                  </tr>
                ))}
                {decision.motivos_de_descarte.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="py-3 text-center text-slate-500">
                      el modelo nunca descarto este origen
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 className="mb-1 text-sm font-semibold">Productos guardados</h3>
          <div className="overflow-x-auto">
            <table className="tabla">
              <thead>
                <tr>
                  <th>producto</th>
                  <th className="text-right">stock prom. (tn)</th>
                  <th className="text-right">pico (tn)</th>
                  <th className="text-right">ingresos (tn)</th>
                </tr>
              </thead>
              <tbody>
                {flujo.productos.map((fila) => (
                  <tr key={fila.producto}>
                    <td>{fila.producto}</td>
                    <td className="text-right">{numero(fila.stock_promedio_tn)}</td>
                    <td className="text-right">{numero(fila.stock_maximo_tn)}</td>
                    <td className="text-right">{numero(fila.ingresos_tn)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function PanelLote({
  lote,
  runId,
  onCerrar,
}: {
  lote: RecorridoLote;
  runId: string;
  onCerrar: () => void;
}) {
  const pedidos = [...new Set(lote.recorrido.map((paso) => paso.codigo_pedido).filter(Boolean))];
  return (
    <div className="fixed inset-y-0 right-0 z-20 w-full max-w-3xl overflow-y-auto border-l border-borde bg-white p-4 shadow-xl">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Lote {lote.id_lote}</h2>
          <p className="text-sm text-slate-500">
            {lote.producto ?? SIN_DATO} · {lote.sitio ?? SIN_DATO} · ingreso dia{" "}
            {numero(lote.dia_ingreso, 0)}
          </p>
        </div>
        <button className="boton" onClick={onCerrar}>
          cerrar
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Caja titulo="Ingresadas" valor={`${numero(lote.toneladas_ingresadas)} tn`} />
        <Caja titulo="Retiradas" valor={`${numero(lote.toneladas_retiradas)} tn`} />
        <Caja titulo="Sin retirar" valor={`${numero(lote.toneladas_sin_retirar)} tn`} />
        <Caja
          titulo="Almacenaje"
          valor={usd(lote.costo_almacenaje_usd)}
          detalle={`${numero(lote.dias_con_cargo_de_almacenaje, 0)} dias con cargo (${numero(
            lote.dia_primer_cargo,
            0,
          )} a ${numero(lote.dia_ultimo_cargo, 0)})`}
        />
      </div>

      <p className="mt-3 text-xs text-slate-500">{lote.nota_recorrido}.</p>

      <h3 className="mt-3 text-sm font-semibold">Recorrido fisico</h3>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr>
              <th className="text-right">dia</th>
              <th>tipo de arco</th>
              <th>origen</th>
              <th>destino</th>
              <th className="text-right">tn</th>
              <th>contenedor</th>
              <th>pedido</th>
            </tr>
          </thead>
          <tbody>
            {lote.recorrido.map((paso, indice) => (
              <tr key={`${paso.tipo_arco}-${paso.dia_inicio}-${paso.id_contenedor}-${indice}`}>
                <td className="text-right">{numero(paso.dia_inicio)}</td>
                <td>{paso.tipo_arco}</td>
                <td>{paso.origen || SIN_DATO}</td>
                <td>{paso.destino || SIN_DATO}</td>
                <td className="text-right">{numero(paso.toneladas)}</td>
                <td>{paso.id_contenedor || SIN_DATO}</td>
                <td>{paso.codigo_pedido || SIN_DATO}</td>
              </tr>
            ))}
            {lote.recorrido.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-4 text-center text-slate-500">
                  el lote tiene cargos pero ningun arco lo movio
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <h3 className="mt-3 text-sm font-semibold">Costo del lote por categoria</h3>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr>
              <th>categoria</th>
              <th className="text-right">importe</th>
              <th className="text-right">cargos</th>
            </tr>
          </thead>
          <tbody>
            {lote.costo_por_categoria.map((fila) => (
              <tr key={fila.categoria}>
                <td>{fila.categoria || SIN_DATO}</td>
                <td className="text-right">{usd(fila.importe_usd)}</td>
                <td className="text-right">{numero(fila.eventos, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">total del lote {usd(lote.costo_total_usd)}.</p>

      {pedidos.length > 0 ? (
        <p className="mt-2 text-xs">
          pedidos que se llevaron este lote:{" "}
          {pedidos.slice(0, 8).map((pedido) => (
            <Link
              key={pedido}
              className="mr-2 text-teal-700 underline"
              href={`/corridas/${encodeURIComponent(runId)}/porque?pedido=${pedido}`}
            >
              {pedido}
            </Link>
          ))}
        </p>
      ) : null}
    </div>
  );
}
