"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Avisos } from "@/components/Avisos";
import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import { TarjetaEstado } from "@/components/Semaforo";
import {
  AgruparPor,
  Dashboard,
  listarCorridas,
  traerDashboard,
  traerRestricciones,
  urlExportacion,
} from "@/lib/api";
import { horas, numero, porcentaje, SIN_DATO, usd } from "@/lib/formato";
import { estadoCapacidad, estadoCosto, estadoRestriccion, estadoServicio } from "@/lib/semaforo";

const OPCIONES_AGRUPAR: { valor: AgruparPor; titulo: string }[] = [
  { valor: "dia", titulo: "día" },
  { valor: "semana", titulo: "semana" },
  { valor: "mes", titulo: "mes" },
  { valor: "anio", titulo: "año" },
];

export default function PaginaCorrida({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agruparPor, setAgruparPor] = useState<AgruparPor>("dia");

  useEffect(() => {
    traerDashboard(runId, agruparPor)
      .then(setDatos)
      .catch((e: Error) => setError(e.message));
  }, [runId, agruparPor]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Corrida {datos.run_id}</h1>
          <p className="text-sm text-slate-500">{datos.tipo}</p>
        </div>
        {datos.tiene_drill_down ? (
          <div className="flex flex-wrap gap-2">
            <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/costos`}>
              Explorar costos
            </Link>
            <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/flujo`}>
              Flujo y almacenaje
            </Link>
            <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/porque`}>
              ¿Por que no se cumplio un pedido?
            </Link>
          </div>
        ) : null}
      </div>

      {datos.tiene_drill_down ? (
        <CorridaAuditada
          runId={runId}
          datos={datos}
          agruparPor={agruparPor}
          onAgruparPor={setAgruparPor}
        />
      ) : (
        <CorridaDeBarrido datos={datos} />
      )}
    </div>
  );
}

function CorridaDeBarrido({ datos }: { datos: Dashboard }) {
  const kpis = Object.entries(datos.kpis_barrido ?? {});

  return (
    <div className="space-y-4">
      <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-alerta">
        {datos.motivo_sin_drill_down}
      </div>
      <section className="panel">
        <h2 className="titulo-panel">KPIs de la corrida</h2>
        <table className="tabla">
          <thead>
            <tr>
              <th>kpi</th>
              <th className="text-right">valor</th>
            </tr>
          </thead>
          <tbody>
            {kpis.map(([kpi, valor]) => (
              <tr key={kpi}>
                <td>{kpi}</td>
                <td className="text-right">{numero(valor, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function CorridaAuditada({
  runId,
  datos,
  agruparPor,
  onAgruparPor,
}: {
  runId: string;
  datos: Dashboard;
  agruparPor: AgruparPor;
  onAgruparPor: (valor: AgruparPor) => void;
}) {
  const { servicio, costos, restriccion, capacidad, inventario, calidad } = datos;

  const grafCostos = useMemo(
    () => ({
      tooltip: { trigger: "item" as const },
      series: [
        {
          type: "pie" as const,
          radius: ["45%", "70%"],
          data: (costos?.por_categoria ?? []).map((c) => ({
            name: c.categoria || "sin categoria",
            value: c.importe_usd,
          })),
        },
      ],
    }),
    [costos],
  );

  const grafMotivos = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      grid: { left: 8, right: 16, bottom: 8, top: 16, containLabel: true },
      xAxis: { type: "value" as const },
      yAxis: {
        type: "category" as const,
        data: (restriccion?.por_motivo ?? []).map((m) => m.codigo_motivo).reverse(),
      },
      series: [
        {
          type: "bar" as const,
          data: (restriccion?.por_motivo ?? []).map((m) => m.alternativas).reverse(),
          itemStyle: { color: "#b45309" },
        },
      ],
    }),
    [restriccion],
  );

  const grafInventario = useMemo(
    () => ({
      tooltip: {
        trigger: "axis" as const,
        formatter: (partes: unknown) => {
          const fila = (Array.isArray(partes) ? partes[0] : partes) as {
            dataIndex: number;
            axisValue: string;
          };
          const punto = (inventario?.serie ?? [])[fila.dataIndex];
          if (!punto) return fila.axisValue;
          const rango =
            punto.dias > 1 ? `${punto.fecha_desde ?? ""} a ${punto.fecha_hasta ?? ""}` : "";
          return [
            `<strong>${fila.axisValue}</strong>${rango ? ` (${rango})` : ""}`,
            `stock físico: ${numero(punto.stock_fisico_tn)} tn${
              punto.dias > 1 ? ` (promedio de ${punto.dias} días, pico ${numero(punto.stock_fisico_tn_pico)} tn)` : ""
            }`,
          ].join("<br/>");
        },
      },
      grid: { left: 8, right: 16, bottom: 8, top: 16, containLabel: true },
      xAxis: {
        type: "category" as const,
        data: (inventario?.serie ?? []).map((f) => f.periodo),
      },
      yAxis: { type: "value" as const, name: "tn" },
      series: [
        {
          name: "stock fisico",
          type: "line" as const,
          smooth: true,
          data: (inventario?.serie ?? []).map((f) => f.stock_fisico_tn),
          itemStyle: { color: "#0f766e" },
        },
      ],
    }),
    [inventario],
  );

  return (
    <div className="space-y-6">
      {calidad && calidad.mensajes.length > 0 ? (
        <section className="panel space-y-2">
          <h2 className="titulo-panel">Calidad del import ({calidad.estado_ultima_importacion})</h2>
          <Avisos mensajes={calidad.mensajes} />
        </section>
      ) : null}

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Resumen — corrida {runId}
        </h2>
        <NivelUno runId={runId} datos={datos} />
      </div>

      <div id="servicio-y-cumplimiento">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Servicio y cumplimiento
        </h2>
        <Rejilla>
          <Kpi
            titulo="Toneladas entregadas"
            valor={numero(servicio?.toneladas_entregadas)}
            detalle={`asignadas ${numero(servicio?.toneladas_asignadas)}`}
          />
          <Kpi
            titulo="Ciclo real promedio"
            valor={`${numero(servicio?.dias_ciclo_promedio)} dias`}
          />
          <Kpi
            titulo="Contenedores entregados"
            valor={numero(servicio?.contenedores_entregados, 0)}
            detalle={`creados ${numero(servicio?.contenedores_creados, 0)}`}
          />
          <Kpi
            titulo="Filas con descuadre"
            valor={numero(inventario?.filas_con_descuadre, 0)}
            tono={inventario && inventario.filas_con_descuadre > 0 ? "critico" : "normal"}
            detalle="C-12 exige descuadre_tn = 0"
          />
        </Rejilla>
      </div>

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Costo</h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <section className="panel">
            <h2 className="titulo-panel">Costo de caja por categoria</h2>
            <Grafico opcion={grafCostos} />
          </section>
          <section className="panel">
            <h2 className="titulo-panel">Motivos de descarte de alternativas</h2>
            <Grafico opcion={grafMotivos} />
          </section>
        </div>
      </div>

      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Capacidad e inventario
      </h2>
      <section className="panel">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="titulo-panel mb-0">
            Stock físico por {OPCIONES_AGRUPAR.find((o) => o.valor === agruparPor)?.titulo}
          </h2>
          {inventario?.tiene_fecha_calendario ? (
            <div className="flex items-center gap-1 text-xs text-slate-500">
              ver por:
              {OPCIONES_AGRUPAR.map((opcion) => (
                <button
                  key={opcion.valor}
                  className="boton"
                  aria-pressed={agruparPor === opcion.valor}
                  onClick={() => onAgruparPor(opcion.valor)}
                  style={
                    agruparPor === opcion.valor
                      ? { background: "#0f766e", color: "white", borderColor: "#0f766e" }
                      : undefined
                  }
                >
                  {opcion.titulo}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        {!inventario?.tiene_fecha_calendario ? (
          <p className="mb-2 text-xs text-slate-500">
            esta corrida se importó con un esquema anterior a ADR-064.2 y no trae fecha calendario:
            solo se puede ver por día de campaña.
          </p>
        ) : null}
        <Grafico opcion={grafInventario} />
      </section>

      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Restricciones
      </h2>
      <section className="panel">
        <h2 className="titulo-panel">Esperas fisicas</h2>
        <table className="tabla">
          <thead>
            <tr>
              <th>tipo de arco</th>
              <th className="text-right">eventos</th>
              <th className="text-right">espera promedio</th>
              <th className="text-right">espera maxima</th>
            </tr>
          </thead>
          <tbody>
            {(restriccion?.esperas ?? []).map((espera) => (
              <tr key={espera.tipo_arco}>
                <td>{espera.tipo_arco}</td>
                <td className="text-right">{espera.eventos}</td>
                <td className="text-right">{horas(espera.espera_promedio_horas)}</td>
                <td className="text-right">{horas(espera.espera_maxima_horas)}</td>
              </tr>
            ))}
            {(restriccion?.esperas ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="text-center text-slate-500">
                  la corrida no registro esperas
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Capacidad por recurso ({capacidad?.dias} dias)</h2>
        <table className="tabla">
          <thead>
            <tr>
              <th>recurso</th>
              <th>ubicacion</th>
              <th className="text-right">nominal</th>
              <th className="text-right">ocupacion promedio</th>
              <th className="text-right">pico</th>
              <th className="text-right">uso pico</th>
              <th className="text-right">cola maxima</th>
            </tr>
          </thead>
          <tbody>
            {(capacidad?.por_recurso ?? []).map((fila) => (
              <tr key={`${fila.tipo_recurso}-${fila.ubicacion}`}>
                <td>{fila.tipo_recurso}</td>
                <td>{fila.ubicacion}</td>
                <td className="text-right">{numero(fila.capacidad_nominal)}</td>
                <td className="text-right">{numero(fila.ocupacion_promedio)}</td>
                <td className="text-right">{numero(fila.ocupacion_maxima)}</td>
                <td className="text-right">{porcentaje(fila.uso_pico_pct)}</td>
                <td className="text-right">{numero(fila.cola_maxima)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Exportar tablas</h2>
        <div className="flex flex-wrap gap-2">
          {["decisiones", "asignaciones", "arcos", "costos", "inventario", "capacidad"].map(
            (tabla) => (
              <a key={tabla} className="boton" href={urlExportacion(runId, tabla)}>
                {tabla}.csv
              </a>
            ),
          )}
          <a
            className="boton"
            href={urlExportacion(runId, "costos", { tipo_contable: "CAJA" })}
          >
            costos (solo caja).csv
          </a>
        </div>
      </section>
    </div>
  );
}

interface PuntoResumen {
  run_id: string;
  nivel_servicio: number | null;
  costo_usd_tn: number | null;
  sobrecosto_total_usd: number | null;
  uso_pico_pct: number | null;
}

/** Junta lo que ya calculan /dashboard/ y /cost-explorer/constraints/ para un punto de la serie:
 * ningun endpoint nuevo, solo dos llamadas que ya existian por separado (en /costos). */
async function resumenDeCorrida(runId: string): Promise<PuntoResumen> {
  const [dashboard, restricciones] = await Promise.all([
    traerDashboard(runId),
    traerRestricciones(runId).catch(() => null),
  ]);
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

function variacionPct(anterior: number | null, actual: number | null): number | null {
  if (anterior === null || actual === null || anterior === 0) return null;
  return (100 * (actual - anterior)) / anterior;
}

function textoDelta(variacion: number | null, unidad: string, contraRunId?: string): string | undefined {
  if (variacion === null || !contraRunId) return undefined;
  const flecha = variacion >= 0 ? "▲" : "▼";
  return `${flecha} ${numero(Math.abs(variacion))} ${unidad} vs ${contraRunId}`;
}

/** Nivel 1 (MOD v4.0): 4 numeros grandes con estado y tendencia contra las corridas anteriores
 * del mismo escenario. No agrega ningun dato nuevo: reordena /dashboard/ y /constraints/ que ya
 * existian, ahora comparados entre corridas en vez de leidos una por una. */
function NivelUno({ runId, datos }: { runId: string; datos: Dashboard }) {
  const [serie, setSerie] = useState<PuntoResumen[] | null>(null);

  useEffect(() => {
    let vigente = true;
    setSerie(null);
    listarCorridas()
      .then(async (todas) => {
        const actual = todas.find((c) => c.run_id === runId);
        if (!actual) return;
        const hermanas = todas
          .filter((c) => c.escenario === actual.escenario && c.tiene_drill_down)
          .sort((a, b) => (a.replica ?? 0) - (b.replica ?? 0));
        const indice = hermanas.findIndex((c) => c.run_id === runId);
        const ventana = indice === -1 ? [actual] : hermanas.slice(Math.max(0, indice - 3), indice + 1);
        const puntos = await Promise.all(ventana.map((c) => resumenDeCorrida(c.run_id)));
        if (vigente) setSerie(puntos);
      })
      .catch(() => vigente && setSerie(null));
    return () => {
      vigente = false;
    };
  }, [runId]);

  const anterior = serie && serie.length >= 2 ? serie[serie.length - 2] : null;
  const actualEnSerie = serie && serie.length >= 1 ? serie[serie.length - 1] : null;

  const varServicio = variacionPct(anterior?.nivel_servicio ?? null, actualEnSerie?.nivel_servicio ?? null);
  const varCosto = variacionPct(anterior?.costo_usd_tn ?? null, actualEnSerie?.costo_usd_tn ?? null);
  const varSobrecosto = variacionPct(
    anterior?.sobrecosto_total_usd ?? null,
    actualEnSerie?.sobrecosto_total_usd ?? null,
  );
  const varUso = variacionPct(anterior?.uso_pico_pct ?? null, actualEnSerie?.uso_pico_pct ?? null);

  const usoPico = Math.max(
    0,
    ...(datos.capacidad?.por_recurso ?? []).map((r) => r.uso_pico_pct ?? 0),
  );
  const tieneUso = (datos.capacidad?.por_recurso ?? []).some((r) => r.uso_pico_pct !== null);

  return (
    <Rejilla>
      <TarjetaEstado
        titulo="Servicio"
        valor={porcentaje(datos.servicio?.nivel_servicio ?? null, true)}
        detalle="nivel de servicio"
        estado={estadoServicio(datos.servicio?.nivel_servicio ?? null)}
        serie={serie?.map((p) => p.nivel_servicio)}
        delta={textoDelta(varServicio, "pp", anterior?.run_id)}
        href="#servicio-y-cumplimiento"
      />
      <TarjetaEstado
        titulo="Costo"
        valor={usd(datos.costos?.costo_usd_tn)}
        detalle="USD/tn"
        estado={estadoCosto(varCosto)}
        serie={serie?.map((p) => p.costo_usd_tn)}
        delta={textoDelta(varCosto, "%", anterior?.run_id)}
        href={`/corridas/${encodeURIComponent(runId)}/costo`}
      />
      <TarjetaEstado
        titulo="Restricción"
        valor={numero(datos.restriccion?.mas_baratas_no_factibles, 0)}
        detalle="alternativas más baratas no factibles"
        estado={estadoRestriccion(datos.restriccion?.mas_baratas_no_factibles ?? null)}
        serie={serie?.map((p) => p.sobrecosto_total_usd)}
        delta={textoDelta(varSobrecosto, "% sobrecosto", anterior?.run_id)}
        href={`/corridas/${encodeURIComponent(runId)}/restricciones`}
      />
      <TarjetaEstado
        titulo="Capacidad e inventario"
        valor={tieneUso ? `${numero(usoPico)} %` : SIN_DATO}
        detalle="ocupación pico"
        estado={estadoCapacidad(tieneUso ? usoPico : null)}
        serie={serie?.map((p) => p.uso_pico_pct)}
        delta={textoDelta(varUso, "pp", anterior?.run_id)}
        href={`/corridas/${encodeURIComponent(runId)}/almacenaje`}
      />
    </Rejilla>
  );
}
