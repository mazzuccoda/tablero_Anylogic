"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import { Dashboard, Restricciones, traerDashboard, traerRestricciones } from "@/lib/api";
import { horas, numero, SIN_DATO, usd } from "@/lib/formato";

interface Datos {
  dashboard: Dashboard;
  restricciones: Restricciones;
}

export default function PaginaRestriccionesNivel2({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    Promise.all([traerDashboard(runId), traerRestricciones(runId)])
      .then(([dashboard, restricciones]) => {
        if (vigente) setDatos({ dashboard, restricciones });
      })
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId]);

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
          itemStyle: { color: "#9c4327" },
        },
      ],
    };
  }, [datos]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  const { dashboard, restricciones } = datos;
  const { restriccion } = dashboard;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Restricciones — {runId}</h1>
          <p className="text-sm text-slate-500">nivel 2 · qué está limitando la red y cuánto cuesta</p>
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
        <Kpi
          titulo="Sobrecosto total"
          valor={usd(restricciones.sobrecosto_total_usd)}
          tono={restricciones.sobrecosto_total_usd > 0 ? "alerta" : "normal"}
          detalle={`${numero(restricciones.decisiones_afectadas, 0)} decisiones`}
        />
        <Kpi
          titulo="Alternativas más baratas no factibles"
          valor={numero(restriccion?.mas_baratas_no_factibles, 0)}
          tono={restriccion && restriccion.mas_baratas_no_factibles > 0 ? "alerta" : "normal"}
          detalle={`en ${numero(restriccion?.pedidos_con_alternativa_mas_barata_no_factible, 0)} pedidos`}
        />
        <Kpi titulo="Alternativas evaluadas" valor={numero(restriccion?.alternativas_evaluadas, 0)} />
        <Kpi titulo="No factibles" valor={numero(restriccion?.alternativas_no_factibles, 0)} />
      </Rejilla>

      <section className="panel">
        <h2 className="titulo-panel">Sobrecosto por motivo</h2>
        <p className="mb-2 text-xs text-slate-500">{restricciones.definicion}</p>
        <Grafico opcion={grafRestricciones} alto={240} />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="panel">
          <h2 className="titulo-panel">Esperas físicas</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th>tipo de arco</th>
                <th className="text-right">eventos</th>
                <th className="text-right">promedio</th>
                <th className="text-right">máxima</th>
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
                  <td colSpan={4} className="py-4 text-center text-slate-500">
                    la corrida no registró esperas
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2 className="titulo-panel">Pedidos con la restricción más cara</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th>pedido</th>
                <th>motivo</th>
                <th className="text-right">sobrecosto</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {restricciones.decisiones.slice(0, 8).map((fila) => (
                <tr key={fila.id_decision}>
                  <td>{fila.codigo_pedido}</td>
                  <td>{fila.codigo_motivo}</td>
                  <td className="text-right text-alerta">{usd(fila.sobrecosto_usd)}</td>
                  <td>
                    <Link
                      className="text-acento underline"
                      href={`/corridas/${encodeURIComponent(runId)}/porque?pedido=${fila.codigo_pedido}`}
                    >
                      ver por qué
                    </Link>
                  </td>
                </tr>
              ))}
              {restricciones.decisiones.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-slate-500">
                    ninguna restricción encareció la solución en esta corrida
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>
      </div>

      <section className="panel">
        <h2 className="titulo-panel">Motivos de descarte</h2>
        <table className="tabla">
          <thead>
            <tr>
              <th>motivo</th>
              <th className="text-right">alternativas</th>
            </tr>
          </thead>
          <tbody>
            {(restriccion?.por_motivo ?? []).map((m) => (
              <tr key={m.codigo_motivo}>
                <td>{m.codigo_motivo || SIN_DATO}</td>
                <td className="text-right">{numero(m.alternativas, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
