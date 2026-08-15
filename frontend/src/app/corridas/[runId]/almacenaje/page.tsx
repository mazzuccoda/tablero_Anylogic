"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Grafico } from "@/components/Grafico";
import { Kpi, Rejilla } from "@/components/Kpi";
import { AlmacenajePorProducto, Deposito, traerAlmacenajePorProducto, traerDepositos } from "@/lib/api";
import { numero, porcentaje, SIN_DATO, usd } from "@/lib/formato";

interface Datos {
  almacenaje: AlmacenajePorProducto;
  depositos: Deposito[];
}

function colorOcupacion(pct: number | null): string {
  if (pct === null) return "#94a3b8";
  if (pct >= 100) return "#b91c1c";
  if (pct >= 80) return "#b45309";
  return "#15803d";
}

export default function PaginaAlmacenajeNivel2({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    Promise.all([
      traerAlmacenajePorProducto(runId, { tipo_contable: "CAJA" }),
      traerDepositos(runId),
    ])
      .then(([almacenaje, depositosResp]) => {
        if (vigente) setDatos({ almacenaje, depositos: depositosResp.depositos });
      })
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
  }, [runId]);

  const grafProductos = useMemo(() => {
    const filas = (datos?.almacenaje.filas ?? []).slice(0, 10);
    return {
      tooltip: { trigger: "axis" as const },
      grid: { left: 8, right: 16, bottom: 8, top: 16, containLabel: true },
      xAxis: { type: "value" as const, name: "USD" },
      yAxis: { type: "category" as const, data: filas.map((f) => f.producto).reverse() },
      series: [
        {
          type: "bar" as const,
          data: filas.map((f) => f.costo_almacenaje_usd).reverse(),
          itemStyle: { color: "#0f766e" },
        },
      ],
    };
  }, [datos]);

  if (error) return <p className="text-critico">{error}</p>;
  if (!datos) return <p className="text-slate-500">cargando...</p>;

  const { almacenaje, depositos } = datos;
  const ocupacionPico = depositos.reduce(
    (max, d) => (d.ocupacion_pico_pct !== null && d.ocupacion_pico_pct > max ? d.ocupacion_pico_pct : max),
    0,
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Almacenaje — {runId}</h1>
          <p className="text-sm text-slate-500">nivel 2 · distribución, ocupación y costo de guardar stock</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}`}>
            volver al resumen
          </Link>
          <Link className="boton" href={`/corridas/${encodeURIComponent(runId)}/flujo`}>
            explorar depósitos (nivel 3)
          </Link>
        </div>
      </div>

      <Rejilla>
        <Kpi
          titulo="Costo de almacenaje (caja)"
          valor={usd(almacenaje.costo_almacenaje_total_usd)}
          detalle={`${almacenaje.dias_de_la_corrida} días de corrida`}
        />
        <Kpi
          titulo="Ocupación pico"
          valor={porcentaje(ocupacionPico || null)}
          tono={ocupacionPico >= 100 ? "critico" : ocupacionPico >= 80 ? "alerta" : "normal"}
          detalle={`${depositos.length} depósito(s) declarados`}
        />
        <Kpi titulo="Días promedio en depósito" detalle={almacenaje.base_dias} valor={numero(promedioPonderado(almacenaje), 1)} />
        <Kpi
          titulo="Descuadre vs. snapshot"
          valor={usd(almacenaje.descuadre_contra_snapshot.diferencia_usd ?? null)}
          tono={
            almacenaje.descuadre_contra_snapshot.diferencia_usd &&
            Math.abs(almacenaje.descuadre_contra_snapshot.diferencia_usd) > 0
              ? "alerta"
              : "normal"
          }
          detalle={almacenaje.descuadre_contra_snapshot.nota ?? `${almacenaje.descuadre_contra_snapshot.filas_declaradas} filas declaradas`}
        />
      </Rejilla>

      <section className="panel">
        <h2 className="titulo-panel">Stock vs. capacidad por depósito</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {depositos.map((d) => (
            <div key={d.ubicacion} className="rounded border border-slate-200 p-3">
              <div className="flex items-baseline justify-between">
                <span className="font-medium">{d.ubicacion}</span>
                <span className="text-xs text-slate-500">{d.tipo_ubicacion}</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded bg-slate-100">
                <div
                  className="h-full"
                  style={{
                    width: `${Math.min(d.ocupacion_pico_pct ?? 0, 100)}%`,
                    backgroundColor: colorOcupacion(d.ocupacion_pico_pct),
                  }}
                />
              </div>
              <div className="mt-1 flex items-baseline justify-between text-xs text-slate-500">
                <span>{d.stock_maximo_tn !== null ? `${numero(d.stock_maximo_tn, 0)} tn máx` : SIN_DATO}</span>
                <span>{d.capacidad_tn !== null ? `de ${numero(d.capacidad_tn, 0)} tn` : "sin capacidad declarada"}</span>
                <span>{porcentaje(d.ocupacion_pico_pct)}</span>
              </div>
              <div className="mt-1 flex items-baseline justify-between text-xs text-slate-500">
                <span>{d.productos} producto(s)</span>
                <span>{usd(d.costo_almacenaje_usd)}</span>
              </div>
            </div>
          ))}
          {depositos.length === 0 ? <p className="text-sm text-slate-500">sin depósitos declarados</p> : null}
        </div>
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Costo de almacenaje por producto</h2>
        <Grafico opcion={grafProductos} alto={240} />
      </section>

      <section className="panel">
        <h2 className="titulo-panel">Detalle por producto</h2>
        <table className="tabla">
          <thead>
            <tr>
              <th>producto</th>
              <th className="text-right">ingresos tn</th>
              <th className="text-right">stock promedio tn</th>
              <th className="text-right">stock máximo tn</th>
              <th className="text-right">días en depósito</th>
              <th className="text-right">costo</th>
              <th className="text-right">USD/tn ingresada</th>
              <th className="text-right">%</th>
            </tr>
          </thead>
          <tbody>
            {almacenaje.filas.map((f) => (
              <tr key={f.producto}>
                <td>{f.producto || SIN_DATO}</td>
                <td className="text-right">{numero(f.ingresos_tn)}</td>
                <td className="text-right">{numero(f.stock_promedio_tn)}</td>
                <td className="text-right">{numero(f.stock_maximo_tn)}</td>
                <td className="text-right">{numero(f.dias_promedio_deposito, 1)}</td>
                <td className="text-right">{usd(f.costo_almacenaje_usd)}</td>
                <td className="text-right">{usd(f.usd_por_tn_ingresada)}</td>
                <td className="text-right">{porcentaje(f.porcentaje)}</td>
              </tr>
            ))}
            {almacenaje.filas.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-4 text-center text-slate-500">
                  sin datos de almacenaje
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">
          base de días: {almacenaje.base_dias} · base de egresos: {almacenaje.base_egresos} · depósitos:{" "}
          {almacenaje.depositos.join(", ") || SIN_DATO}
        </p>
      </section>
    </div>
  );
}

function promedioPonderado(almacenaje: AlmacenajePorProducto): number | null {
  const filas = almacenaje.filas.filter((f) => f.dias_promedio_deposito !== null && f.ingresos_tn);
  const totalTn = filas.reduce((s, f) => s + (f.ingresos_tn ?? 0), 0);
  if (totalTn <= 0) return null;
  const suma = filas.reduce((s, f) => s + (f.dias_promedio_deposito ?? 0) * (f.ingresos_tn ?? 0), 0);
  return suma / totalTn;
}
