"use client";

import Link from "next/link";
import { useState } from "react";

import { Avisos } from "@/components/Avisos";
import {
  API,
  ErrorApi,
  Importacion,
  Mensaje,
  detalleErrorApi,
  leerCuerpoRespuesta,
} from "@/lib/api";

export default function PaginaImportar() {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [resultado, setResultado] = useState<Importacion | null>(null);
  const [rechazo, setRechazo] = useState<Mensaje[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!archivo) return;

    setSubiendo(true);
    setResultado(null);
    setRechazo(null);
    setError(null);

    const cuerpo = new FormData();
    cuerpo.append("archivo", archivo);

    try {
      const respuesta = await fetch(`${API}/imports/upload/`, { method: "POST", body: cuerpo });
      const datos = await leerCuerpoRespuesta(respuesta);
      const mensajes =
        datos && typeof datos === "object" && "mensajes" in datos
          ? (datos.mensajes as Mensaje[])
          : null;
      if (!respuesta.ok && mensajes) {
        setRechazo(mensajes);
      } else if (respuesta.status === 422) {
        setRechazo([{ nivel: "ERROR", texto: detalleErrorApi(datos, respuesta.status) }]);
      } else if (!respuesta.ok) {
        throw new ErrorApi(respuesta.status, datos, detalleErrorApi(datos, respuesta.status));
      } else {
        setResultado(datos as Importacion);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Importar resultados</h1>
        <p className="text-sm text-slate-500">
          Un .zip con el paquete de auditoria (las seis tablas + esquema_auditoria.json +
          manifiesto_auditoria_&lt;run_id&gt;.json) o el kpis_por_corrida.csv del barrido.
        </p>
      </div>

      <form className="panel flex items-center gap-3" onSubmit={enviar}>
        <input
          type="file"
          accept=".zip,.csv"
          className="campo"
          onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
        />
        <button className="boton-primario" disabled={!archivo || subiendo}>
          {subiendo ? "importando..." : "importar"}
        </button>
      </form>

      {error ? <p className="text-critico">{error}</p> : null}

      {rechazo ? (
        <section className="panel space-y-2">
          <h2 className="titulo-panel">La importacion no se pudo completar</h2>
          <Avisos mensajes={rechazo} />
        </section>
      ) : null}

      {resultado ? (
        <section className="panel space-y-3">
          <h2 className="titulo-panel">
            {resultado.estado.replace(/_/g, " ").toLowerCase()}
            {resultado.run_id ? ` — ${resultado.run_id}` : ""}
          </h2>

          <table className="tabla">
            <thead>
              <tr>
                <th>archivo</th>
                <th>tabla</th>
                <th>filas importadas</th>
                <th>filas del manifiesto</th>
              </tr>
            </thead>
            <tbody>
              {resultado.archivos.map((archivo) => (
                <tr key={archivo.nombre}>
                  <td>{archivo.nombre}</td>
                  <td>{archivo.tabla}</td>
                  <td>{archivo.filas_importadas}</td>
                  <td>
                    {archivo.filas_manifiesto === null || archivo.filas_manifiesto < 0
                      ? "no declarado"
                      : archivo.filas_manifiesto}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Avisos mensajes={resultado.mensajes} />

          {resultado.run_id ? (
            <Link
              className="text-acento underline"
              href={`/corridas/${encodeURIComponent(resultado.run_id)}`}
            >
              ver el tablero de {resultado.run_id}
            </Link>
          ) : (
            <Link className="text-acento underline" href="/">
              ver las corridas importadas
            </Link>
          )}
        </section>
      ) : null}
    </div>
  );
}
