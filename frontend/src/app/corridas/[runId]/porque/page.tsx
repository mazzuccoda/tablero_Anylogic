"use client";

import { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";

import { Kpi, Rejilla } from "@/components/Kpi";
import { Tabla } from "@/components/Tabla";
import { Alternativa, Arco, Cargo, PorQue, traerPorQue } from "@/lib/api";
import { booleano, horas, numero, usd } from "@/lib/formato";

const COLUMNAS_ALTERNATIVAS: ColumnDef<Alternativa, unknown>[] = [
  { header: "ronda", accessorKey: "ronda" },
  { header: "ranking", accessorKey: "orden_ranking" },
  { header: "alternativa", accessorKey: "id_alternativa" },
  { header: "circuito", accessorKey: "circuito" },
  { header: "origen", accessorKey: "origen_stock" },
  {
    header: "usd/tn",
    accessorKey: "costo_incremental_usd_tn",
    cell: (c) => numero(c.getValue() as number | null),
  },
  { header: "factible", accessorKey: "factible", cell: (c) => booleano(c.getValue() as boolean) },
  { header: "resultado", accessorKey: "resultado_ejecucion" },
  { header: "motivo", accessorKey: "codigo_motivo" },
  {
    header: "mas barata no factible",
    accessorKey: "es_mas_barata_no_factible",
    cell: (c) =>
      c.getValue() ? <span className="font-semibold text-alerta">si</span> : booleano(false),
  },
];

const COLUMNAS_ARCOS: ColumnDef<Arco, unknown>[] = [
  { header: "arco", accessorKey: "tipo_arco" },
  { header: "origen", accessorKey: "origen" },
  { header: "destino", accessorKey: "destino" },
  { header: "inicio", accessorKey: "dia_inicio", cell: (c) => numero(c.getValue() as number) },
  { header: "fin", accessorKey: "dia_fin", cell: (c) => numero(c.getValue() as number) },
  {
    header: "real",
    accessorKey: "duracion_real_horas",
    cell: (c) => horas(c.getValue() as number | null),
  },
  {
    header: "esperada",
    id: "esperada",
    cell: ({ row }) =>
      horas(row.original.duracion_esperada_horas, row.original.duracion_esperada_aplica),
  },
  { header: "recurso", accessorKey: "recurso_utilizado" },
  { header: "estado", accessorKey: "estado_final" },
];

const COLUMNAS_CARGOS: ColumnDef<Cargo, unknown>[] = [
  { header: "cargo", accessorKey: "id_costo" },
  { header: "dia", accessorKey: "dia", cell: (c) => numero(c.getValue() as number) },
  { header: "tipo contable", accessorKey: "tipo_contable" },
  { header: "categoria", accessorKey: "categoria" },
  { header: "alcance", accessorKey: "alcance" },
  { header: "cantidad", accessorKey: "cantidad", cell: (c) => numero(c.getValue() as number) },
  { header: "tarifa", accessorKey: "tarifa", cell: (c) => numero(c.getValue() as number) },
  { header: "importe", accessorKey: "importe_usd", cell: (c) => usd(c.getValue() as number) },
];

export default function PaginaPorQue({ params }: { params: { runId: string } }) {
  const runId = decodeURIComponent(params.runId);
  const [pedido, setPedido] = useState("");
  const [datos, setDatos] = useState<PorQue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buscando, setBuscando] = useState(false);

  async function buscar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!pedido.trim()) return;

    setBuscando(true);
    setError(null);
    setDatos(null);
    try {
      setDatos(await traerPorQue(runId, pedido.trim()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBuscando(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">
          ¿Por que se atraso o no se cumplio este pedido?
        </h1>
        <p className="text-sm text-slate-500">Corrida {runId}</p>
      </div>

      <form className="panel flex items-center gap-3" onSubmit={buscar}>
        <input
          className="campo w-64"
          placeholder="codigo_pedido (por ejemplo P-0001)"
          value={pedido}
          onChange={(e) => setPedido(e.target.value)}
        />
        <button className="boton-primario" disabled={buscando}>
          {buscando ? "buscando..." : "buscar"}
        </button>
      </form>

      {error ? <p className="text-critico">{error}</p> : null}

      {datos ? (
        <div className="space-y-6">
          <Rejilla>
            <Kpi
              titulo="Alternativas evaluadas"
              valor={numero(datos.resumen.alternativas_evaluadas, 0)}
              detalle={`no factibles ${numero(datos.resumen.alternativas_no_factibles, 0)}`}
            />
            <Kpi
              titulo="Sobrecosto de la restriccion"
              valor={
                datos.resumen.sobrecosto_de_la_restriccion_usd_tn === null
                  ? "no aplica"
                  : `${numero(datos.resumen.sobrecosto_de_la_restriccion_usd_tn)} usd/tn`
              }
              tono={datos.resumen.hay_mas_barata_no_factible ? "alerta" : "normal"}
              detalle="elegida menos la mas barata no factible"
            />
            <Kpi titulo="Costo de caja del pedido" valor={usd(datos.resumen.costo_caja_usd)} />
            <Kpi
              titulo="Horas de espera"
              valor={horas(datos.resumen.horas_de_espera)}
              detalle={`arcos mas largos de lo esperado: ${datos.resumen.arcos_fuera_de_lo_esperado}`}
            />
          </Rejilla>

          <section className="panel">
            <h2 className="titulo-panel">Alternativas evaluadas</h2>
            <Tabla columnas={COLUMNAS_ALTERNATIVAS} datos={datos.decisiones} />
          </section>

          <section className="panel">
            <h2 className="titulo-panel">Arcos fisicos ejecutados</h2>
            <Tabla columnas={COLUMNAS_ARCOS} datos={datos.arcos} buscador={false} />
          </section>

          <section className="panel">
            <h2 className="titulo-panel">Cargos</h2>
            <Tabla columnas={COLUMNAS_CARGOS} datos={datos.cargos} buscador={false} />
            <p className="mt-2 text-xs text-slate-500">
              Los cargos ECONOMICO son costo de oportunidad y no suman al total de caja.
            </p>
          </section>
        </div>
      ) : null}
    </div>
  );
}
