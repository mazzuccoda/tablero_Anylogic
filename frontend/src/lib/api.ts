export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ErrorApi extends Error {
  constructor(
    public readonly estado: number,
    public readonly cuerpo: unknown,
    mensaje: string,
  ) {
    super(mensaje);
  }
}

export async function leerCuerpoRespuesta(respuesta: Response): Promise<unknown> {
  const texto = await respuesta.text();
  if (!texto) return null;

  const tipoContenido = respuesta.headers.get("content-type") ?? "";
  if (tipoContenido.includes("application/json")) {
    return JSON.parse(texto);
  }

  try {
    return JSON.parse(texto);
  } catch {
    return texto;
  }
}

export function detalleErrorApi(cuerpo: unknown, estado: number): string {
  if (cuerpo && typeof cuerpo === "object") {
    const datos = cuerpo as { detalle?: unknown; detail?: unknown };
    if (typeof datos.detalle === "string") return datos.detalle;
    if (typeof datos.detail === "string") return datos.detail;
  }

  if (typeof cuerpo === "string") {
    if (cuerpo.trimStart().toLowerCase().startsWith("<!doctype")) {
      return (
        `el servidor respondio HTML en vez de JSON (HTTP ${estado}). ` +
        "Revisar que NEXT_PUBLIC_API_URL apunte al backend /api/v1 y que el proxy permita el tamano del ZIP."
      );
    }
    return cuerpo.slice(0, 300);
  }

  return `error ${estado}`;
}

export async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const respuesta = await fetch(`${API}${ruta}`, { cache: "no-store", ...init });
  const cuerpo = await leerCuerpoRespuesta(respuesta);

  if (!respuesta.ok) {
    const detalle = detalleErrorApi(cuerpo, respuesta.status);
    throw new ErrorApi(respuesta.status, cuerpo, detalle);
  }

  return cuerpo as T;
}

export interface Corrida {
  id: number;
  run_id: string;
  escenario: string;
  replica: number | null;
  tipo: "AUDITORIA" | "BARRIDO";
  nivel_auditoria: string;
  version_esquema: string;
  version_modelo: string;
  duracion_campania_dias: number | null;
  importado: string;
  tiene_drill_down: boolean;
}

export interface Mensaje {
  nivel: "ERROR" | "ADVERTENCIA" | "INFO";
  texto: string;
  tabla?: string;
}

export interface Dashboard {
  run_id: string;
  tipo: string;
  tiene_drill_down: boolean;
  motivo_sin_drill_down?: string;
  kpis_barrido?: Record<string, number | null>;
  servicio?: {
    nivel_servicio: number | null;
    atraso_promedio_dias: number | null;
    toneladas_asignadas: number;
    toneladas_entregadas: number;
    cobertura_entrega: number | null;
    dias_ciclo_promedio: number | null;
    contenedores_creados: number;
    contenedores_entregados: number;
    asignaciones: number;
    asignaciones_cerradas: number;
    asignaciones_canceladas: number;
  };
  costos?: {
    costo_total_caja_usd: number;
    costo_total_economico_usd: number;
    costo_usd_tn: number | null;
    toneladas_entregadas: number;
    por_categoria: { categoria: string; importe_usd: number }[];
    cargos_caja: number;
    cargos_economicos: number;
  };
  restriccion?: {
    alternativas_evaluadas: number;
    alternativas_no_factibles: number;
    alternativas_intentadas_fallidas: number;
    mas_baratas_no_factibles: number;
    pedidos_con_alternativa_mas_barata_no_factible: number;
    por_motivo: { codigo_motivo: string; alternativas: number }[];
    esperas: {
      tipo_arco: string;
      eventos: number;
      espera_promedio_horas: number | null;
      espera_maxima_horas: number | null;
    }[];
  };
  capacidad?: {
    dias: number;
    por_recurso: {
      tipo_recurso: string;
      ubicacion: string;
      capacidad_nominal: number | null;
      ocupacion_promedio: number | null;
      ocupacion_maxima: number | null;
      cola_maxima: number | null;
      uso_pico_pct: number | null;
    }[];
  };
  inventario?: {
    serie_diaria: { dia: number; stock_fisico_tn: number; stock_libre_tn: number }[];
    ocupacion_pico_pct: number | null;
    filas_con_descuadre: number;
  };
  calidad?: {
    estado_ultima_importacion: string | null;
    version_esquema: string;
    mensajes: Mensaje[];
    filas_por_tabla: Record<string, number>;
  };
}

export interface Alternativa {
  id: number;
  id_decision: string;
  ronda: number | null;
  id_alternativa: string;
  codigo_pedido: string;
  producto: string;
  circuito: string;
  origen_stock: string;
  factible: boolean | null;
  orden_ranking: number | null;
  resultado_ejecucion: string;
  codigo_motivo: string;
  detalle_motivo: string;
  costo_incremental_usd_tn: number | null;
  es_mas_barata_no_factible: boolean | null;
  holgura_estimada_dias: number | null;
  llega_a_tiempo_estimado: boolean | null;
  toneladas_factibles: number | null;
  toneladas_tomadas: number | null;
}

export interface Asignacion {
  id_asignacion: string;
  codigo_pedido: string;
  producto: string;
  origen: string;
  circuito: string;
  toneladas_asignadas: number | null;
  toneladas_entregadas: number | null;
  dias_ciclo_real: number | null;
  costo_incremental_estimado: number | null;
  costo_real_contenedores_usd: number | null;
  desvio_costo_usd: number | null;
  cerrada: boolean | null;
  cancelada: boolean | null;
}

export interface Arco {
  id_evento_arco: string;
  tipo_arco: string;
  origen: string;
  destino: string;
  toneladas: number | null;
  dia_inicio: number | null;
  dia_fin: number | null;
  duracion_real_horas: number | null;
  duracion_esperada_horas: number | null;
  duracion_esperada_aplica: boolean;
  recurso_utilizado: string;
  estado_final: string;
}

export interface Cargo {
  id_costo: string;
  dia: number | null;
  tipo_contable: string;
  categoria: string;
  alcance: string;
  cantidad: number | null;
  tarifa: number | null;
  importe_usd: number | null;
}

export interface PorQue {
  run_id: string;
  codigo_pedido: string;
  resumen: {
    alternativas_evaluadas: number;
    alternativas_no_factibles: number;
    hay_mas_barata_no_factible: boolean;
    sobrecosto_de_la_restriccion_usd_tn: number | null;
    costo_caja_usd: number;
    horas_de_espera: number | null;
    arcos_fuera_de_lo_esperado: number;
  };
  decisiones: Alternativa[];
  asignaciones: Asignacion[];
  arcos: Arco[];
  cargos: Cargo[];
}

export interface Comparacion {
  a: { run_id: string; escenario: string };
  b: { run_id: string; escenario: string };
  sin_kpis: boolean;
  kpis: {
    kpi: string;
    a: number | null;
    b: number | null;
    diferencia: number | null;
    variacion_pct: number | null;
  }[];
}

export interface Importacion {
  id: number;
  estado: string;
  run_id: string;
  version_esquema: string;
  mensajes: Mensaje[];
  filas_por_tabla: Record<string, number>;
  archivos: {
    nombre: string;
    tabla: string;
    filas_importadas: number;
    filas_manifiesto: number | null;
  }[];
}

export const listarCorridas = () =>
  pedir<{ results: Corrida[] }>("/simulation-runs/?limit=200").then((r) => r.results);

export const traerDashboard = (runId: string) =>
  pedir<Dashboard>(`/simulation-runs/${encodeURIComponent(runId)}/dashboard/`);

export const traerPorQue = (runId: string, pedido: string) =>
  pedir<PorQue>(
    `/orders/${encodeURIComponent(pedido)}/why/?run_id=${encodeURIComponent(runId)}`,
  );

export const comparar = (a: string, b: string) =>
  pedir<Comparacion>("/comparisons/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_a: a, run_b: b }),
  });

export const urlExportacion = (runId: string, tabla: string, filtros: Record<string, string> = {}) => {
  const query = new URLSearchParams(filtros).toString();
  return `${API}/simulation-runs/${encodeURIComponent(runId)}/export/${tabla}/${query ? `?${query}` : ""}`;
};
