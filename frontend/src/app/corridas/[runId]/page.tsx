"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Avisos } from "@/components/Avisos";
import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import { Dashboard, traerDashboard, urlExportacion } from "@/lib/api";
import { horas, numero, porcentaje, usd } from "@/lib/formato";

export default function PaginaCorrida({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    traerDashboard(runId)
      .then(setDatos)
      .catch((e: Error) => setError(e.message));
  }, [runId]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Corrida {datos.run_id}</h1>
          <p className="text-sm text-slate-500">{datos.tipo}</p>
        </div>
        {datos.tiene_drill_down ? (
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/porque`}>
            ¿Por que no se cumplio un pedido?
          </Link>
        ) : null}
      </div>

      {datos.tiene_drill_down ? (
        <CorridaAuditada runId={runId} datos={datos} />
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

function CorridaAuditada({ runId, datos }: { runId: string; datos: Dashboard }) {
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
      tooltip: { trigger: "axis" as const },
      grid: { left: 8, right: 16, bottom: 8, top: 16, containLabel: true },
      xAxis: {
        type: "category" as const,
        data: (inventario?.serie_diaria ?? []).map((f) => f.dia),
      },
      yAxis: { type: "value" as const, name: "tn" },
      series: [
        {
          name: "stock fisico",
          type: "line" as const,
          smooth: true,
          data: (inventario?.serie_diaria ?? []).map((f) => f.stock_fisico_tn),
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

      <Rejilla>
        <Kpi
          titulo="Nivel de servicio"
          valor={porcentaje(servicio?.nivel_servicio ?? null, true)}
          detalle="del modelo, no recalculado"
        />
        <Kpi
          titulo="Costo total (caja)"
          valor={usd(costos?.costo_total_caja_usd)}
          detalle={`solo tipo_contable = CAJA; economico ${usd(costos?.costo_total_economico_usd)}`}
        />
        <Kpi titulo="Costo por tonelada" valor={usd(costos?.costo_usd_tn)} />
        <Kpi
          titulo="Alternativas mas baratas no factibles"
          valor={numero(restriccion?.mas_baratas_no_factibles, 0)}
          tono={restriccion && restriccion.mas_baratas_no_factibles > 0 ? "alerta" : "normal"}
          detalle={`en ${numero(
            restriccion?.pedidos_con_alternativa_mas_barata_no_factible,
            0,
          )} pedidos`}
        />
      </Rejilla>

      <Rejilla>
        <Kpi
          titulo="Toneladas entregadas"
          valor={numero(servicio?.toneladas_entregadas)}
          detalle={`asignadas ${numero(servicio?.toneladas_asignadas)}`}
        />
        <Kpi titulo="Ciclo real promedio" valor={`${numero(servicio?.dias_ciclo_promedio)} dias`} />
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

      <section className="panel">
        <h2 className="titulo-panel">Stock fisico por dia</h2>
        <Grafico opcion={grafInventario} />
      </section>

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
