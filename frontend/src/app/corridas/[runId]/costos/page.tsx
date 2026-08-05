"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import {
  Eventos,
  FilaArco,
  FilaCategoria,
  FilaDimension,
  FilaEtapa,
  FilaObjeto,
  Metrica,
  Reconciliacion,
  Restricciones,
  ResumenCostos,
  Waterfall,
  traerEventosCosto,
  traerPorArco,
  traerPorCategoria,
  traerPorDimension,
  traerPorEtapa,
  traerPorObjeto,
  traerReconciliacion,
  traerRestricciones,
  traerResumenCostos,
  traerWaterfall,
  urlExportacion,
} from "@/lib/api";
import { numero, porcentaje, SIN_DATO, usd } from "@/lib/formato";

/** Los filtros son texto libre a proposito: la API valida el nombre del campo, no el valor.
 * Un valor que no existe devuelve el desglose vacio con `filas_consideradas = 0`, y la pantalla
 * lo dice en vez de mostrar un panel en cero como si el costo fuera cero. */
type Filtros = {
  tipo_contable: string;
  etapa: string;
  producto: string;
  circuito: string;
  sitio: string;
  dia_desde: string;
  dia_hasta: string;
};

const FILTROS_VACIOS: Filtros = {
  tipo_contable: "CAJA",
  etapa: "",
  producto: "",
  circuito: "",
  sitio: "",
  dia_desde: "",
  dia_hasta: "",
};

const OBJETOS = [
  { objeto: "lote", clave: "id_lote", titulo: "Lote" },
  { objeto: "contenedor", clave: "id_contenedor", titulo: "Contenedor" },
  { objeto: "pedido", clave: "codigo_pedido", titulo: "Pedido" },
] as const;

type Objeto = (typeof OBJETOS)[number];

interface Datos {
  resumen: ResumenCostos;
  waterfall: Waterfall;
  etapas: FilaEtapa[];
  categorias: FilaCategoria[];
  productos: FilaDimension[];
  circuitos: FilaDimension[];
  sitios: FilaDimension[];
  arcos: { filas: FilaArco[]; nodo_usd: number; arco_usd: number };
  objetos: FilaObjeto[];
  objetos_sin_toneladas: number;
  base_objeto: string;
  reconciliacion: Reconciliacion;
  restricciones: Restricciones;
}

function comoQuery(filtros: Filtros): Record<string, string> {
  return Object.fromEntries(
    Object.entries(filtros).filter(([, valor]) => valor !== ""),
  ) as Record<string, string>;
}

/** La exportacion CSV filtra por columnas del modelo: `etapa` y el rango de dias no existen ahi,
 * asi que no se mandan en vez de que el backend los ignore en silencio. */
function filtrosExportables(filtros: Filtros): Record<string, string> {
  const { tipo_contable, producto, circuito, sitio } = filtros;
  return comoQuery({ ...FILTROS_VACIOS, tipo_contable, producto, circuito, sitio });
}

function baseDe(metrica: Metrica): string {
  return `base: ${metrica.base.nombre} = ${numero(metrica.base.valor)}`;
}

export default function PaginaCostos({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VACIOS);
  const [aplicados, setAplicados] = useState<Filtros>(FILTROS_VACIOS);
  const [objeto, setObjeto] = useState<Objeto>(OBJETOS[2]);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detalle, setDetalle] = useState<{ titulo: string; eventos: Eventos } | null>(null);

  const query = useMemo(() => comoQuery(aplicados), [aplicados]);

  useEffect(() => {
    let vigente = true;
    setError(null);
    Promise.all([
      traerResumenCostos(runId, query),
      traerWaterfall(runId, query),
      traerPorEtapa(runId, query),
      traerPorCategoria(runId, query),
      traerPorDimension(runId, "producto", query),
      traerPorDimension(runId, "circuito", query),
      traerPorDimension(runId, "sitio", query),
      traerPorArco(runId, query),
      traerPorObjeto(runId, objeto.objeto, query),
      traerReconciliacion(runId, query),
      traerRestricciones(runId),
    ])
      .then(
        ([
          resumen,
          waterfall,
          etapas,
          categorias,
          productos,
          circuitos,
          sitios,
          arcos,
          porObjeto,
          reconciliacion,
          restricciones,
        ]) => {
          if (!vigente) return;
          setDatos({
            resumen,
            waterfall,
            etapas: etapas.filas,
            categorias: categorias.filas,
            productos: productos.filas,
            circuitos: circuitos.filas,
            sitios: sitios.filas,
            arcos: { filas: arcos.filas, nodo_usd: arcos.nodo_usd, arco_usd: arcos.arco_usd },
            objetos: porObjeto.filas,
            objetos_sin_toneladas: porObjeto.objetos_sin_toneladas,
            base_objeto: porObjeto.base,
            reconciliacion,
            restricciones,
          });
        },
      )
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId, query, objeto]);

  const abrirDetalle = useCallback(
    (campo: string, valor: string) => {
      traerEventosCosto(runId, { ...query, [campo]: valor, limit: "50", orden: "importe" })
        .then((eventos) => setDetalle({ titulo: `${campo} = ${valor}`, eventos }))
        .catch((e: Error) => setError(e.message));
    },
    [runId, query],
  );

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
          itemStyle: { color: "#0f766e" },
          data: pasos.map((p) => p.importe_usd ?? 0),
        },
      ],
    };
  }, [datos]);

  const grafRestricciones = useMemo(() => {
    const filas = (datos?.restricciones.por_restriccion ?? []).slice(0, 10);
    return {
      tooltip: { trigger: "axis" as const },
      grid: { left: 8, right: 16, bottom: 8, top: 16, containLabel: true },
      xAxis: { type: "value" as const, name: "USD" },
      yAxis: { type: "category" as const, data: filas.map((f) => f.codigo_motivo).reverse() },
      series: [
        {
          type: "bar" as const,
          data: filas.map((f) => f.sobrecosto_usd).reverse(),
          itemStyle: { color: "#b45309" },
        },
      ],
    };
  }, [datos]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  const { resumen, reconciliacion, restricciones } = datos;
  const vacio = resumen.filas_consideradas === 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Costos de {resumen.run_id}</h1>
          <p className="text-sm text-slate-500">
            escenario {resumen.escenario} · replica {numero(resumen.replica, 0)} · importes de
            costos_eventos, {resumen.tipo_contable}
          </p>
        </div>
        <div className="flex gap-2">
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}`}>
            volver al dashboard
          </Link>
          <a
            className="boton"
            title="la exportacion filtra por columnas de costos_eventos: etapa y rango de dias no viajan"
            href={urlExportacion(runId, "costos", filtrosExportables(aplicados))}
          >
            exportar costos.csv
          </a>
        </div>
      </div>

      <PanelFiltros
        filtros={filtros}
        etapas={datos.etapas.map((e) => e.etapa)}
        onCambio={setFiltros}
        onAplicar={() => setAplicados(filtros)}
        onLimpiar={() => {
          setFiltros(FILTROS_VACIOS);
          setAplicados(FILTROS_VACIOS);
        }}
      />

      {vacio ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-alerta">
          el recorte no dejo ninguna fila de costos_eventos: no es que el costo sea cero, es que
          ningun cargo cumple estos filtros. Los valores de texto no se validan contra la corrida,
          asi que revisar que {JSON.stringify(resumen.filtros_aplicados)} exista en el paquete.
        </div>
      ) : null}

      <Rejilla>
        <Kpi
          titulo={`Costo ${resumen.tipo_contable}`}
          valor={usd(resumen.importe_usd)}
          detalle={`${numero(resumen.eventos, 0)} cargos · ${
            resumen.contraparte.tipo_contable
          } ${usd(resumen.contraparte.importe_usd)} (no se suma)`}
        />
        <Kpi
          titulo="USD por tonelada"
          valor={usd(resumen.usd_por_tn.valor)}
          detalle={baseDe(resumen.usd_por_tn)}
        />
        <Kpi
          titulo="USD por contenedor"
          valor={usd(resumen.usd_por_contenedor.valor)}
          detalle={baseDe(resumen.usd_por_contenedor)}
        />
        <Kpi
          titulo="USD por pedido"
          valor={usd(resumen.usd_por_pedido.valor)}
          detalle={baseDe(resumen.usd_por_pedido)}
        />
      </Rejilla>

      <Rejilla>
        <Kpi
          titulo="Etapa mas cara"
          valor={resumen.etapa_principal?.etapa ?? SIN_DATO}
          detalle={`${usd(resumen.etapa_principal?.importe_usd)} · ${porcentaje(
            resumen.etapa_principal?.porcentaje,
          )}`}
        />
        <Kpi
          titulo="Circuito mas caro"
          valor={String(resumen.circuito_mas_caro?.circuito ?? SIN_DATO)}
          detalle={usd(resumen.circuito_mas_caro?.importe_usd)}
        />
        <Kpi
          titulo="Producto mas caro"
          valor={String(resumen.producto_mas_caro?.producto ?? SIN_DATO)}
          detalle={usd(resumen.producto_mas_caro?.importe_usd)}
        />
        <Kpi
          titulo="Costo sin etapa"
          valor={usd(resumen.etapa_no_clasificada_usd)}
          tono={(resumen.etapa_no_clasificada_usd ?? 0) > 0 ? "alerta" : "normal"}
          detalle="categorias que el mapa de etapas no conoce"
        />
      </Rejilla>

      <section className="panel">
        <h2 className="titulo-panel">Cascada por etapa logistica</h2>
        <Grafico opcion={grafWaterfall} alto={320} />
        <p className="mt-2 text-xs text-slate-500">
          total {usd(datos.waterfall.total_usd)}: es la suma de los pasos, no un numero aparte. El
          USD/tn de cada etapa tiene su propia base fisica, asi que no se suman ratios.
        </p>
      </section>

      <TablaEtapas
        etapas={datos.etapas}
        categorias={datos.categorias}
        onFiltrarEtapa={(etapa) => {
          const nuevos = { ...FILTROS_VACIOS, ...aplicados, etapa };
          setFiltros(nuevos);
          setAplicados(nuevos);
        }}
        onVerEventos={(campo, valor) => abrirDetalle(campo, valor)}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <TablaDimension
          titulo="Producto"
          campo="producto"
          filas={datos.productos}
          onFiltrar={(valor) => {
            const nuevos = { ...aplicados, producto: valor };
            setFiltros(nuevos);
            setAplicados(nuevos);
          }}
        />
        <TablaDimension
          titulo="Circuito"
          campo="circuito"
          filas={datos.circuitos}
          onFiltrar={(valor) => {
            const nuevos = { ...aplicados, circuito: valor };
            setFiltros(nuevos);
            setAplicados(nuevos);
          }}
        />
        <TablaDimension
          titulo="Ubicacion (sitio)"
          campo="sitio"
          filas={datos.sitios}
          onFiltrar={(valor) => {
            const nuevos = { ...aplicados, sitio: valor };
            setFiltros(nuevos);
            setAplicados(nuevos);
          }}
        />
      </div>

      <section className="panel">
        <h2 className="titulo-panel">Nodo o tramo</h2>
        <p className="mb-2 text-xs text-slate-500">
          quieto en un nodo {usd(datos.arcos.nodo_usd)} · moviendose {usd(datos.arcos.arco_usd)}. Un
          par origen = destino no es un arco: es lo que cuesta estar ahi.
        </p>
        <table className="tabla">
          <thead>
            <tr>
              <th>origen</th>
              <th>destino</th>
              <th>tipo</th>
              <th className="text-right">importe</th>
              <th className="text-right">%</th>
              <th className="text-right">cargos</th>
            </tr>
          </thead>
          <tbody>
            {datos.arcos.filas.slice(0, 20).map((fila) => (
              <tr key={`${fila.origen}-${fila.destino}`}>
                <td>{fila.origen || SIN_DATO}</td>
                <td>{fila.destino || SIN_DATO}</td>
                <td>{fila.tipo}</td>
                <td className="text-right">{usd(fila.importe_usd)}</td>
                <td className="text-right">{porcentaje(fila.porcentaje)}</td>
                <td className="text-right">{numero(fila.eventos, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h2 className="titulo-panel mb-0">Costo por objeto</h2>
          {OBJETOS.map((opcion) => (
            <button
              key={opcion.objeto}
              className="boton"
              aria-pressed={objeto.objeto === opcion.objeto}
              onClick={() => setObjeto(opcion)}
              style={
                objeto.objeto === opcion.objeto
                  ? { background: "#0f766e", color: "white", borderColor: "#0f766e" }
                  : undefined
              }
            >
              {opcion.titulo}
            </button>
          ))}
        </div>
        <p className="mb-2 text-xs text-slate-500">
          USD/tn de cada {objeto.titulo.toLowerCase()} = importe del objeto / {datos.base_objeto}.
          {datos.objetos_sin_toneladas > 0
            ? ` ${datos.objetos_sin_toneladas} sin toneladas conocidas: se muestran "sin dato", no cero.`
            : ""}
        </p>
        <table className="tabla">
          <thead>
            <tr>
              <th>{objeto.clave}</th>
              <th className="text-right">importe</th>
              <th className="text-right">toneladas</th>
              <th className="text-right">USD/tn</th>
              <th className="text-right">cargos</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {datos.objetos.slice(0, 25).map((fila) => {
              const id = String(fila[objeto.clave] ?? "");
              return (
                <tr key={id}>
                  <td>{id || SIN_DATO}</td>
                  <td className="text-right">{usd(fila.importe_usd)}</td>
                  <td className="text-right">{numero(fila.toneladas)}</td>
                  <td className="text-right">{usd(fila.usd_por_tn)}</td>
                  <td className="text-right">{numero(fila.eventos, 0)}</td>
                  <td className="text-right">
                    <button className="boton" onClick={() => abrirDetalle(objeto.clave, id)}>
                      eventos
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Sobrecosto de las restricciones</h2>
        <p className="mb-2 text-xs text-slate-500">{restricciones.definicion}</p>
        <Rejilla>
          <Kpi
            titulo="Sobrecosto total"
            valor={usd(restricciones.sobrecosto_total_usd)}
            tono={restricciones.sobrecosto_total_usd > 0 ? "alerta" : "normal"}
            detalle={`${numero(restricciones.decisiones_afectadas, 0)} decisiones`}
          />
          <Kpi
            titulo="Restriccion mas cara"
            valor={restricciones.por_restriccion[0]?.codigo_motivo ?? SIN_DATO}
            detalle={usd(restricciones.por_restriccion[0]?.sobrecosto_usd)}
          />
          <Kpi
            titulo="Sobrecosto por tonelada"
            valor={usd(restricciones.por_restriccion[0]?.sobrecosto_usd_tn)}
            detalle="de la restriccion mas cara, sobre las toneladas afectadas"
          />
          <Kpi
            titulo="Pedidos alcanzados"
            valor={numero(restricciones.por_restriccion[0]?.pedidos, 0)}
            detalle="por la restriccion mas cara"
          />
        </Rejilla>
        <div className="mt-4">
          <Grafico opcion={grafRestricciones} alto={220} />
        </div>
        <table className="tabla mt-2">
          <thead>
            <tr>
              <th>decision</th>
              <th>pedido</th>
              <th>restriccion</th>
              <th>origen elegido</th>
              <th>origen bloqueado</th>
              <th className="text-right">elegida USD/tn</th>
              <th className="text-right">sin restriccion</th>
              <th className="text-right">sobrecosto</th>
            </tr>
          </thead>
          <tbody>
            {restricciones.decisiones.slice(0, 15).map((fila) => (
              <tr key={fila.id_decision}>
                <td>{fila.id_decision}</td>
                <td>
                  <Link
                    className="text-teal-700 underline"
                    href={`/corridas/${encodeURIComponent(runId)}/porque?pedido=${fila.codigo_pedido}`}
                  >
                    {fila.codigo_pedido}
                  </Link>
                </td>
                <td>{fila.codigo_motivo}</td>
                <td>{fila.origen_elegido || SIN_DATO}</td>
                <td>{fila.origen_bloqueado || SIN_DATO}</td>
                <td className="text-right">{usd(fila.costo_elegida_usd_tn)}</td>
                <td className="text-right">{usd(fila.costo_sin_restriccion_usd_tn)}</td>
                <td className="text-right text-alerta">{usd(fila.sobrecosto_usd)}</td>
              </tr>
            ))}
            {restricciones.decisiones.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-4 text-center text-slate-500">
                  ninguna restriccion encarecio la solucion en esta corrida
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Reconciliacion</h2>
        <p className="mb-2 text-xs text-slate-500">
          total {usd(reconciliacion.total_usd)}. Las dimensiones que el contrato escribe en toda
          fila tienen que dar exacto; las que solo existen en algunos cargos son parciales por
          definicion y dicen cuanto queda afuera.
        </p>
        <table className="tabla">
          <thead>
            <tr>
              <th>dimension</th>
              <th className="text-right">suma</th>
              <th className="text-right">diferencia</th>
              <th>estado</th>
              <th>motivo</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(reconciliacion.dimensiones).map(([dimension, fila]) => (
              <tr key={dimension}>
                <td>{dimension}</td>
                <td className="text-right">{usd(fila.suma)}</td>
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
                <td className="text-xs text-slate-500">{fila.motivo ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {reconciliacion.categorias_sin_clasificar.length > 0 ? (
          <p className="mt-2 text-sm text-alerta">
            categorias que el mapa de etapas no conoce:{" "}
            {reconciliacion.categorias_sin_clasificar
              .map((c) => `${c.categoria || SIN_DATO} (${usd(c.importe_usd)})`)
              .join(", ")}
          </p>
        ) : null}
      </section>

      {detalle ? (
        <PanelEventos detalle={detalle} onCerrar={() => setDetalle(null)} />
      ) : null}
    </div>
  );
}

function PanelFiltros({
  filtros,
  etapas,
  onCambio,
  onAplicar,
  onLimpiar,
}: {
  filtros: Filtros;
  etapas: string[];
  onCambio: (filtros: Filtros) => void;
  onAplicar: () => void;
  onLimpiar: () => void;
}) {
  const campo = (clave: keyof Filtros, etiqueta: string, placeholder = "") => (
    <label className="text-xs text-slate-500">
      {etiqueta}
      <input
        className="campo mt-1 block w-full"
        placeholder={placeholder}
        value={filtros[clave]}
        onChange={(e) => onCambio({ ...filtros, [clave]: e.target.value })}
      />
    </label>
  );

  return (
    <section className="panel">
      <h2 className="titulo-panel">Filtros</h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-7">
        <label className="text-xs text-slate-500">
          tipo contable
          <select
            className="campo mt-1 block w-full"
            value={filtros.tipo_contable}
            onChange={(e) => onCambio({ ...filtros, tipo_contable: e.target.value })}
          >
            <option value="CAJA">CAJA</option>
            <option value="ECONOMICO">ECONOMICO</option>
          </select>
        </label>
        <label className="text-xs text-slate-500">
          etapa
          <select
            className="campo mt-1 block w-full"
            value={filtros.etapa}
            onChange={(e) => onCambio({ ...filtros, etapa: e.target.value })}
          >
            <option value="">todas</option>
            {etapas.map((etapa) => (
              <option key={etapa} value={etapa}>
                {etapa}
              </option>
            ))}
          </select>
        </label>
        {campo("producto", "producto", "JUGO")}
        {campo("circuito", "circuito", "CONSOLIDACION_DEPOSITO")}
        {campo("sitio", "sitio", "RUTA9")}
        {campo("dia_desde", "dia desde", "0")}
        {campo("dia_hasta", "dia hasta", "365")}
      </div>
      <div className="mt-3 flex gap-2">
        <button className="boton" onClick={onAplicar}>
          aplicar
        </button>
        <button className="boton" onClick={onLimpiar}>
          limpiar
        </button>
      </div>
    </section>
  );
}

function TablaEtapas({
  etapas,
  categorias,
  onFiltrarEtapa,
  onVerEventos,
}: {
  etapas: FilaEtapa[];
  categorias: FilaCategoria[];
  onFiltrarEtapa: (etapa: string) => void;
  onVerEventos: (campo: string, valor: string) => void;
}) {
  const [abiertas, setAbiertas] = useState<string[]>([]);

  return (
    <section className="panel">
      <h2 className="titulo-panel">Etapa y categoria</h2>
      <table className="tabla">
        <thead>
          <tr>
            <th>etapa</th>
            <th className="text-right">importe</th>
            <th className="text-right">%</th>
            <th className="text-right">cargos</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {etapas.map((etapa) => {
            const abierta = abiertas.includes(etapa.etapa);
            const hijas = categorias.filter((c) => c.etapa === etapa.etapa);
            return (
              <Fragment key={etapa.etapa}>
                <tr className="hover:bg-slate-50">
                  <td>
                    <button
                      className="mr-2 text-slate-500"
                      aria-label={abierta ? "cerrar" : "abrir"}
                      onClick={() =>
                        setAbiertas(
                          abierta
                            ? abiertas.filter((e) => e !== etapa.etapa)
                            : [...abiertas, etapa.etapa],
                        )
                      }
                    >
                      {abierta ? "▾" : "▸"}
                    </button>
                    {etapa.etapa}
                  </td>
                  <td className="text-right">{usd(etapa.importe_usd)}</td>
                  <td className="text-right">{porcentaje(etapa.porcentaje)}</td>
                  <td className="text-right">{numero(etapa.eventos, 0)}</td>
                  <td className="text-right">
                    <button className="boton" onClick={() => onFiltrarEtapa(etapa.etapa)}>
                      filtrar
                    </button>
                  </td>
                </tr>
                {abierta
                  ? hijas.map((categoria) => (
                      <tr key={`${etapa.etapa}-${categoria.categoria}`} className="bg-slate-50">
                        <td className="pl-8 text-slate-600">{categoria.categoria}</td>
                        <td className="text-right">{usd(categoria.importe_usd)}</td>
                        <td className="text-right">{porcentaje(categoria.porcentaje)}</td>
                        <td className="text-right">{numero(categoria.eventos, 0)}</td>
                        <td className="text-right">
                          <button
                            className="boton"
                            onClick={() => onVerEventos("categoria", categoria.categoria)}
                          >
                            eventos
                          </button>
                        </td>
                      </tr>
                    ))
                  : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function TablaDimension({
  titulo,
  campo,
  filas,
  onFiltrar,
}: {
  titulo: string;
  campo: string;
  filas: FilaDimension[];
  onFiltrar: (valor: string) => void;
}) {
  return (
    <section className="panel">
      <h2 className="titulo-panel">{titulo}</h2>
      <table className="tabla">
        <thead>
          <tr>
            <th>{campo}</th>
            <th className="text-right">importe</th>
            <th className="text-right">%</th>
          </tr>
        </thead>
        <tbody>
          {filas.slice(0, 12).map((fila) => {
            const valor = String(fila[campo] ?? "");
            return (
              <tr key={valor} className="cursor-pointer hover:bg-slate-50" onClick={() => onFiltrar(valor)}>
                <td>{valor || SIN_DATO}</td>
                <td className="text-right">{usd(fila.importe_usd)}</td>
                <td className="text-right">{porcentaje(fila.porcentaje)}</td>
              </tr>
            );
          })}
          {filas.length === 0 ? (
            <tr>
              <td colSpan={3} className="py-4 text-center text-slate-500">
                sin filas con estos filtros
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </section>
  );
}

function PanelEventos({
  detalle,
  onCerrar,
}: {
  detalle: { titulo: string; eventos: Eventos };
  onCerrar: () => void;
}) {
  const { titulo, eventos } = detalle;
  return (
    <div className="fixed inset-y-0 right-0 z-20 w-full max-w-3xl overflow-y-auto border-l border-slate-200 bg-white p-4 shadow-xl">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">Eventos contables</h2>
          <p className="text-sm text-slate-500">
            {titulo} · {numero(eventos.total, 0)} cargos, se muestran {eventos.filas.length}
          </p>
        </div>
        <button className="boton" onClick={onCerrar}>
          cerrar
        </button>
      </div>
      <table className="tabla">
        <thead>
          <tr>
            <th>id_costo</th>
            <th className="text-right">dia</th>
            <th>etapa</th>
            <th>categoria</th>
            <th>pedido</th>
            <th>unidad</th>
            <th className="text-right">cantidad</th>
            <th className="text-right">tarifa</th>
            <th className="text-right">importe</th>
          </tr>
        </thead>
        <tbody>
          {eventos.filas.map((fila) => (
            <tr key={fila.id_costo}>
              <td>{fila.id_costo}</td>
              <td className="text-right">{numero(fila.dia)}</td>
              <td>{fila.etapa}</td>
              <td>{fila.categoria}</td>
              <td>{fila.codigo_pedido || SIN_DATO}</td>
              <td>{fila.unidad}</td>
              <td className="text-right">{numero(fila.cantidad)}</td>
              <td className="text-right">{numero(fila.tarifa)}</td>
              <td className="text-right">{usd(fila.importe_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
