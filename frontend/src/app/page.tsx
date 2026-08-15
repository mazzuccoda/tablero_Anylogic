"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PildoraEstado } from "@/components/Semaforo";
import { Corrida, Dashboard, listarCorridas, traerDashboard } from "@/lib/api";
import { fecha, numero, porcentaje, usd } from "@/lib/formato";
import {
  Estado,
  estadoCapacidad,
  estadoRestriccion,
  estadoServicio,
  peorEstado,
} from "@/lib/semaforo";

interface ResumenCorrida {
  corrida: Corrida;
  dashboard: Dashboard | null;
}

export default function PaginaCorridas() {
  const [corridas, setCorridas] = useState<Corrida[]>([]);
  const [resumenes, setResumenes] = useState<ResumenCorrida[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let vigente = true;
    listarCorridas()
      .then(async (lista) => {
        if (!vigente) return;
        setCorridas(lista);
        const auditadas = lista.filter((c) => c.tiene_drill_down);
        const detalles = await Promise.all(
          auditadas.map(async (corrida): Promise<ResumenCorrida> => {
            try {
              return { corrida, dashboard: await traerDashboard(corrida.run_id) };
            } catch {
              return { corrida, dashboard: null };
            }
          }),
        );
        if (vigente) setResumenes(detalles);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, []);

  if (error) return <p className="text-critico">{error}</p>;
  if (cargando) return <p className="text-slate-500">cargando...</p>;

  if (corridas.length === 0) {
    return (
      <div className="panel">
        Todavia no hay corridas.{" "}
        <Link className="text-acento underline" href="/importar">
          Importar un paquete
        </Link>
        .
      </div>
    );
  }

  const barrido = corridas.filter((c) => !c.tiene_drill_down);
  const alertas = alertasActivas(resumenes);
  const porEscenario = agruparPorEscenario(resumenes);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Portada ejecutiva</h1>
          <p className="text-sm text-slate-500">
            Qué corrida mirar y si algo está roto, antes de entrar a ninguna.
          </p>
        </div>
        <Link className="boton" href="/comparar">
          comparar corridas
        </Link>
      </div>

      <section className="panel space-y-2">
        <h2 className="titulo-panel">Alertas activas</h2>
        {alertas.length === 0 ? (
          <p className="text-sm text-slate-500">sin alertas en las corridas auditadas.</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {alertas.map((a, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: a.estado === "critico" ? "#b91c1c" : "#b45309" }}
                />
                <span>
                  <Link
                    className="font-medium text-acento underline"
                    href={`/corridas/${encodeURIComponent(a.runId)}`}
                  >
                    {a.runId}
                  </Link>{" "}
                  — {a.texto}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {Object.entries(porEscenario).map(([escenario, filas]) => (
        <section key={escenario} className="panel">
          <h2 className="titulo-panel">Escenario {escenario}</h2>
          <div className="divide-y divide-borde">
            {filas.map(({ corrida, dashboard }) => (
              <FilaCorrida key={corrida.run_id} corrida={corrida} dashboard={dashboard} />
            ))}
          </div>
        </section>
      ))}

      {barrido.length > 0 ? (
        <section className="panel">
          <h2 className="titulo-panel">Corridas de barrido</h2>
          <p className="mb-2 text-xs text-slate-500">
            Se ejecutan con nivelAuditoriaRed = DESACTIVADA: tienen KPIs agregados pero no vista
            por pedido.
          </p>
          <table className="tabla">
            <thead>
              <tr>
                <th>run_id</th>
                <th>escenario</th>
                <th>replica</th>
                <th>importada</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {barrido.map((corrida) => (
                <tr key={corrida.run_id}>
                  <td className="font-medium">{corrida.run_id}</td>
                  <td>{corrida.escenario}</td>
                  <td>{corrida.replica ?? "-"}</td>
                  <td>{new Date(corrida.importado).toLocaleString("es-AR")}</td>
                  <td>
                    <Link
                      className="text-acento underline"
                      href={`/corridas/${encodeURIComponent(corrida.run_id)}`}
                    >
                      ver tablero
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </div>
  );
}

function FilaCorrida({
  corrida,
  dashboard,
}: {
  corrida: Corrida;
  dashboard: Dashboard | null;
}) {
  const estado = dashboard ? estadoGlobal(dashboard) : "sin_dato";
  return (
    <div className="grid grid-cols-1 items-center gap-2 py-3 sm:grid-cols-[auto_1fr_auto_auto_auto]">
      <PildoraEstado estado={estado} />
      <div>
        <Link
          className="font-medium text-acento underline"
          href={`/corridas/${encodeURIComponent(corrida.run_id)}`}
        >
          {corrida.run_id}
        </Link>
        <div className="text-xs text-slate-500">
          réplica {corrida.replica ?? "-"}
          {corrida.fecha_inicio_campania
            ? ` · campaña desde ${fecha(corrida.fecha_inicio_campania)}`
            : ""}
        </div>
      </div>
      <div className="text-right text-sm">
        <div className="font-medium">
          {porcentaje(dashboard?.servicio?.nivel_servicio ?? null, true)}
        </div>
        <div className="text-xs text-slate-500">servicio</div>
      </div>
      <div className="text-right text-sm">
        <div className="font-medium">{usd(dashboard?.costos?.costo_usd_tn)}</div>
        <div className="text-xs text-slate-500">USD/tn</div>
      </div>
      <div className="text-right text-sm">
        <div className="font-medium">
          {numero(dashboard?.restriccion?.mas_baratas_no_factibles, 0)}
        </div>
        <div className="text-xs text-slate-500">más baratas no factibles</div>
      </div>
    </div>
  );
}

function estadoGlobal(dashboard: Dashboard): Estado {
  const usos = (dashboard.capacidad?.por_recurso ?? [])
    .map((r) => r.uso_pico_pct)
    .filter((v): v is number => v !== null);
  const estados: Estado[] = [
    estadoServicio(dashboard.servicio?.nivel_servicio ?? null),
    estadoRestriccion(dashboard.restriccion?.mas_baratas_no_factibles ?? null),
    estadoCapacidad(usos.length ? Math.max(...usos) : null),
  ];
  if ((dashboard.inventario?.filas_con_descuadre ?? 0) > 0) estados.push("critico");
  if ((dashboard.calidad?.mensajes ?? []).some((m) => m.nivel === "ADVERTENCIA")) {
    estados.push("atencion");
  }
  return peorEstado(estados);
}

interface Alerta {
  runId: string;
  texto: string;
  estado: "critico" | "atencion";
}

function alertasActivas(resumenes: ResumenCorrida[]): Alerta[] {
  const alertas: Alerta[] = [];
  for (const { corrida, dashboard } of resumenes) {
    if (!dashboard) continue;
    const descuadre = dashboard.inventario?.filas_con_descuadre ?? 0;
    if (descuadre > 0) {
      alertas.push({
        runId: corrida.run_id,
        texto: `${descuadre} filas con descuadre de inventario (C-12 exige 0)`,
        estado: "critico",
      });
    }
    for (const m of dashboard.calidad?.mensajes ?? []) {
      if (m.nivel === "ADVERTENCIA") {
        alertas.push({ runId: corrida.run_id, texto: m.texto, estado: "atencion" });
      }
    }
  }
  return alertas;
}

function agruparPorEscenario(resumenes: ResumenCorrida[]): Record<string, ResumenCorrida[]> {
  const grupos: Record<string, ResumenCorrida[]> = {};
  for (const r of resumenes) {
    (grupos[r.corrida.escenario] ??= []).push(r);
  }
  return grupos;
}
