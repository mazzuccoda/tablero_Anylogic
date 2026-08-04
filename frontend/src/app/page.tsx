"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Corrida, listarCorridas } from "@/lib/api";

export default function PaginaCorridas() {
  const [corridas, setCorridas] = useState<Corrida[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    listarCorridas()
      .then(setCorridas)
      .catch((e: Error) => setError(e.message))
      .finally(() => setCargando(false));
  }, []);

  const auditadas = corridas.filter((c) => c.tiene_drill_down);
  const barrido = corridas.filter((c) => !c.tiene_drill_down);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Corridas importadas</h1>
        <p className="text-sm text-slate-500">
          Las corridas de barrido se ejecutan con nivelAuditoriaRed = DESACTIVADA: tienen KPIs
          agregados pero no vista por pedido.
        </p>
      </div>

      {error ? <p className="text-critico">{error}</p> : null}
      {cargando ? <p className="text-slate-500">cargando...</p> : null}

      {!cargando && corridas.length === 0 ? (
        <div className="panel">
          Todavia no hay corridas.{" "}
          <Link className="text-acento underline" href="/importar">
            Importar un paquete
          </Link>
          .
        </div>
      ) : null}

      {auditadas.length > 0 ? (
        <section className="panel">
          <h2 className="titulo-panel">Corridas auditadas</h2>
          <ListaCorridas corridas={auditadas} />
        </section>
      ) : null}

      {barrido.length > 0 ? (
        <section className="panel">
          <h2 className="titulo-panel">Corridas de barrido</h2>
          <ListaCorridas corridas={barrido} />
        </section>
      ) : null}
    </div>
  );
}

function ListaCorridas({ corridas }: { corridas: Corrida[] }) {
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th>run_id</th>
          <th>escenario</th>
          <th>replica</th>
          <th>nivel de auditoria</th>
          <th>version_esquema</th>
          <th>importada</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {corridas.map((corrida) => (
          <tr key={corrida.run_id}>
            <td className="font-medium">{corrida.run_id}</td>
            <td>{corrida.escenario}</td>
            <td>{corrida.replica ?? "-"}</td>
            <td>{corrida.nivel_auditoria}</td>
            <td>{corrida.version_esquema || corrida.version_modelo || "-"}</td>
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
  );
}
