"use client";

import { useEffect, useState } from "react";

import { Comparacion, Corrida, comparar, listarCorridas } from "@/lib/api";
import { numero } from "@/lib/formato";

export default function PaginaComparar() {
  const [corridas, setCorridas] = useState<Corrida[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [resultado, setResultado] = useState<Comparacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarCorridas()
      .then((lista) => {
        setCorridas(lista);
        if (lista[0]) setA(lista[0].run_id);
        if (lista[1]) setB(lista[1].run_id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function ejecutar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setResultado(null);
    try {
      setResultado(await comparar(a, b));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Comparar dos corridas</h1>
        <p className="text-sm text-slate-500">
          Sobre los KPIs agregados de kpis_por_corrida.csv. El drill-down de decisiones es de una
          corrida auditada a la vez.
        </p>
      </div>

      <form className="panel flex flex-wrap items-center gap-3" onSubmit={ejecutar}>
        <Selector etiqueta="corrida A" valor={a} alCambiar={setA} corridas={corridas} />
        <Selector etiqueta="corrida B" valor={b} alCambiar={setB} corridas={corridas} />
        <button className="boton-primario" disabled={!a || !b}>
          comparar
        </button>
      </form>

      {error ? <p className="text-critico">{error}</p> : null}

      {resultado ? (
        <section className="panel space-y-3">
          <h2 className="titulo-panel">
            {resultado.a.run_id} vs {resultado.b.run_id}
          </h2>

          {resultado.sin_kpis ? (
            <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-alerta">
              Alguna de las dos corridas no tiene KPIs de barrido importados: la comparacion se
              hace sobre kpis_por_corrida.csv.
            </div>
          ) : null}

          <table className="tabla">
            <thead>
              <tr>
                <th>kpi</th>
                <th className="text-right">{resultado.a.run_id}</th>
                <th className="text-right">{resultado.b.run_id}</th>
                <th className="text-right">diferencia</th>
                <th className="text-right">variacion</th>
              </tr>
            </thead>
            <tbody>
              {resultado.kpis.map((fila) => (
                <tr key={fila.kpi}>
                  <td>{fila.kpi}</td>
                  <td className="text-right">{numero(fila.a, 4)}</td>
                  <td className="text-right">{numero(fila.b, 4)}</td>
                  <td className="text-right">{numero(fila.diferencia, 4)}</td>
                  <td className="text-right">
                    {fila.variacion_pct === null ? "sin dato" : `${numero(fila.variacion_pct)} %`}
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

function Selector({
  etiqueta,
  valor,
  alCambiar,
  corridas,
}: {
  etiqueta: string;
  valor: string;
  alCambiar: (valor: string) => void;
  corridas: Corrida[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      {etiqueta}
      <select className="campo" value={valor} onChange={(e) => alCambiar(e.target.value)}>
        {corridas.map((corrida) => (
          <option key={corrida.run_id} value={corrida.run_id}>
            {corrida.run_id}
          </option>
        ))}
      </select>
    </label>
  );
}
