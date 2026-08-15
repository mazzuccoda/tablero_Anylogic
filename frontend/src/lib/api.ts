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
  /** ADR-064.2 (MOD v4.1): null en una corrida importada con un esquema anterior. */
  fecha_inicio_campania: string | null;
  importado: string;
  tiene_drill_down: boolean;
}

/** Agrupacion de series temporales: "dia" es la unica que no necesita fecha_inicio_campania. */
export type AgruparPor = "dia" | "semana" | "mes" | "anio";

export interface Mensaje {
  nivel: "ERROR" | "ADVERTENCIA" | "INFO";
  texto: string;
  tabla?: string;
}

export interface Dashboard {
  run_id: string;
  tipo: string;
  tiene_drill_down: boolean;
  /** ADR-064.2 (MOD v4.1): null en una corrida importada con un esquema anterior. */
  fecha_inicio_campania: string | null;
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
    /** Un periodo (nunca "dia") es el promedio y el pico de sus dias, no la suma (MOD v4.1). */
    serie: {
      periodo: string;
      dia_desde: number | null;
      dia_hasta: number | null;
      fecha_desde: string | null;
      fecha_hasta: string | null;
      dias: number;
      stock_fisico_tn: number | null;
      stock_fisico_tn_pico: number | null;
      stock_libre_tn: number | null;
      stock_libre_tn_pico: number | null;
    }[];
    agrupado_por: AgruparPor;
    tiene_fecha_calendario: boolean;
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

export const traerDashboard = (runId: string, agruparPor: AgruparPor = "dia") =>
  pedir<Dashboard>(
    `/simulation-runs/${encodeURIComponent(runId)}/dashboard/?agrupar_por=${agruparPor}`,
  );

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

/** Un ratio del Cost Explorer siempre viaja con la base fisica sobre la que se dividio. */
export interface Metrica {
  valor: number | null;
  base: { nombre: string; valor: number | null };
}

export interface FilaDimension {
  importe_usd: number | null;
  eventos: number;
  porcentaje: number | null;
  [columna: string]: string | number | null | string[];
}

export interface RespuestaDesglose<T> {
  run_id: string;
  tipo_contable: string;
  filtros_aplicados: Record<string, string | number>;
  filas_consideradas: number;
  importe_considerado: number | null;
  filas: T[];
}

export interface FilaEtapa {
  etapa: string;
  categorias: string[];
  importe_usd: number | null;
  eventos: number;
  porcentaje: number | null;
}

export interface FilaCategoria {
  categoria: string;
  etapa: string;
  importe_usd: number | null;
  eventos: number;
  porcentaje: number | null;
}

export interface FilaArco extends FilaDimension {
  origen: string;
  destino: string;
  tipo: "NODO" | "ARCO" | "GEOGRAFIA_NO_CLASIFICADA";
}

/** ADR-T06 (MOD v6): ruta fisica derivada de ejecucion_arcos ("RUTA9→T4"), no el `circuito`
 * declarado (que es un tipo de consolidacion de 5 valores, no un nombre de trayecto). */
export interface FilaRuta {
  ruta: string;
  importe_usd: number | null;
  eventos: number;
  porcentaje: number | null;
  toneladas: number | null;
  porcentaje_toneladas: number | null;
}

/** ADR-T06: una celda de la matriz "estrategia por producto" (etapa x ruta). */
export interface FilaRutaEtapa {
  ruta: string;
  etapa: string;
  importe_usd: number | null;
  eventos: number;
}

/** MOD v6: cantidad y tarifa promedio ponderada por categoria, para descomponer un cambio de
 * costo entre dos corridas en efecto precio y efecto volumen. Solo tiene sentido a nivel
 * categoria (cada una tiene una unica `unidad`) — nunca a nivel de una dimension como circuito o
 * producto, que mezclan unidades distintas. */
export interface FilaCategoriaCantidad {
  categoria: string;
  etapa: string;
  unidad: string;
  cantidad: number | null;
  tarifa_promedio: number | null;
  importe_usd: number | null;
  eventos: number;
  porcentaje: number | null;
}

export interface FilaObjeto {
  importe_usd: number | null;
  eventos: number;
  toneladas: number | null;
  usd_por_tn: number | null;
  id_lote?: string;
  id_contenedor?: string;
  codigo_pedido?: string;
}

export interface ResumenCostos {
  run_id: string;
  escenario: string;
  replica: number | null;
  tipo_contable: string;
  importe_usd: number | null;
  eventos: number;
  contraparte: { tipo_contable: string; importe_usd: number | null; eventos: number };
  usd_por_tn: Metrica;
  usd_por_contenedor: Metrica;
  usd_por_pedido: Metrica;
  etapa_principal: FilaEtapa | null;
  circuito_mas_caro: FilaDimension | null;
  producto_mas_caro: FilaDimension | null;
  etapa_no_clasificada_usd: number | null;
  filtros_aplicados: Record<string, string | number>;
  filas_consideradas: number;
}

export interface Waterfall {
  run_id: string;
  pasos: {
    etapa: string;
    categorias: string[];
    importe_usd: number | null;
    base: number;
    acumulado: number;
    porcentaje: number | null;
    eventos: number;
  }[];
  total_usd: number | null;
}

export interface Eventos {
  run_id: string;
  orden: string;
  limit: number;
  offset: number;
  total: number;
  filas: {
    id_costo: string;
    dia: number | null;
    categoria: string;
    etapa: string;
    geografia: string;
    codigo_pedido: string;
    id_contenedor: string;
    id_lote: string;
    producto: string;
    circuito: string;
    origen: string;
    destino: string;
    sitio: string;
    unidad: string;
    cantidad: number | null;
    tarifa: number | null;
    importe_usd: number | null;
    motivo: string;
  }[];
}

export interface Restricciones {
  run_id: string;
  sobrecosto_total_usd: number;
  decisiones_afectadas: number;
  definicion: string;
  por_restriccion: {
    codigo_motivo: string;
    sobrecosto_usd: number;
    toneladas: number;
    decisiones: number;
    pedidos: number;
    sobrecosto_usd_tn: number | null;
  }[];
  decisiones: {
    id_decision: string;
    codigo_pedido: string;
    producto: string;
    circuito: string;
    origen_elegido: string;
    origen_bloqueado: string;
    codigo_motivo: string;
    detalle_motivo: string;
    costo_elegida_usd_tn: number;
    costo_sin_restriccion_usd_tn: number;
    sobrecosto_usd_tn: number;
    toneladas: number;
    sobrecosto_usd: number;
  }[];
}

export interface Reconciliacion {
  run_id: string;
  total_usd: number;
  dimensiones: Record<
    string,
    {
      suma: number;
      diferencia: number;
      estado: "EXACTA" | "PARCIAL" | "DESCUADRADA";
      valores: number;
      motivo?: string;
      filas_con_dato?: number;
      importe_sin_dato?: number;
    }
  >;
  dimensiones_descuadradas: string[];
  etapa_no_clasificada_usd: number | null;
  categorias_sin_clasificar: { categoria: string; importe_usd: number | null; eventos: number }[];
}

const rutaCostos = (runId: string, recurso: string, filtros: Record<string, string> = {}) => {
  const query = new URLSearchParams(filtros).toString();
  return `/simulation-runs/${encodeURIComponent(runId)}/cost-explorer/${recurso}${
    query ? `?${query}` : ""
  }`;
};

export const traerResumenCostos = (runId: string, filtros: Record<string, string>) =>
  pedir<ResumenCostos>(rutaCostos(runId, "summary/", filtros));

export const traerWaterfall = (runId: string, filtros: Record<string, string>) =>
  pedir<Waterfall>(rutaCostos(runId, "waterfall/", filtros));

export const traerPorEtapa = (runId: string, filtros: Record<string, string>) =>
  pedir<RespuestaDesglose<FilaEtapa>>(rutaCostos(runId, "by-stage/", filtros));

export const traerPorCategoria = (runId: string, filtros: Record<string, string>) =>
  pedir<RespuestaDesglose<FilaCategoria>>(rutaCostos(runId, "by-category/", filtros));

export const traerPorDimension = (
  runId: string,
  dimension: string,
  filtros: Record<string, string>,
) =>
  pedir<RespuestaDesglose<FilaDimension> & { dimension: string }>(
    rutaCostos(runId, `by-dimension/${dimension}/`, filtros),
  );

export const traerPorArco = (runId: string, filtros: Record<string, string>) =>
  pedir<RespuestaDesglose<FilaArco> & { nodo_usd: number; arco_usd: number }>(
    rutaCostos(runId, "by-arc/", filtros),
  );

export const traerPorRuta = (runId: string, filtros: Record<string, string>) =>
  pedir<RespuestaDesglose<FilaRuta>>(rutaCostos(runId, "by-route/", filtros));

export const traerPorRutaYEtapa = (runId: string, filtros: Record<string, string>) =>
  pedir<RespuestaDesglose<FilaRutaEtapa>>(rutaCostos(runId, "by-route-stage/", filtros));

export const traerPrecioVolumen = (runId: string, filtros: Record<string, string>) =>
  pedir<RespuestaDesglose<FilaCategoriaCantidad>>(rutaCostos(runId, "price-volume/", filtros));

export const traerPorObjeto = (runId: string, objeto: string, filtros: Record<string, string>) =>
  pedir<
    RespuestaDesglose<FilaObjeto> & {
      objeto: string;
      clave: string;
      base: string;
      objetos_sin_toneladas: number;
    }
  >(rutaCostos(runId, `by-object/${objeto}/`, filtros));

export const traerEventosCosto = (runId: string, filtros: Record<string, string>) =>
  pedir<Eventos>(rutaCostos(runId, "events/", filtros));

export const traerRestricciones = (runId: string) =>
  pedir<Restricciones>(rutaCostos(runId, "constraints/"));

export const traerReconciliacion = (runId: string, filtros: Record<string, string>) =>
  pedir<Reconciliacion>(rutaCostos(runId, "reconciliation/", filtros));

export interface EtapaFisica {
  etapa: string;
  toneladas: number | null;
  arcos: number;
  tipos_arco: string[];
  costo_usd: number | null;
  eventos: number;
  categorias: string[];
  usd_por_tn: number | null;
}

export interface Cintas {
  run_id: string;
  tipo_contable: string;
  etapas: EtapaFisica[];
  nodos: { id: string }[];
  cintas: {
    origen: string;
    destino: string;
    producto: string;
    toneladas: number;
    arcos: number;
    tipos_arco: string[];
    etapa: string;
  }[];
  base_cintas: string;
  tipos_arco_no_dibujados: {
    tipo_arco: string;
    toneladas: number;
    arcos: number;
    motivo: string;
  }[];
  toneladas_entregadas: number | null;
  costo_etapas_usd: number;
  almacenamiento_excluido_usd: number | null;
  almacenamiento_eventos: number;
  nota: string;
}

export interface AlmacenajePorProducto {
  run_id: string;
  dias_de_la_corrida: number;
  costo_almacenaje_total_usd: number | null;
  filas: {
    producto: string;
    ingresos_tn: number | null;
    egresos_tn: number | null;
    stock_promedio_tn: number | null;
    stock_maximo_tn: number | null;
    dias_promedio_deposito: number | null;
    toneladas_dia: number | null;
    costo_almacenaje_usd: number | null;
    eventos: number;
    usd_por_tn_ingresada: number | null;
    porcentaje: number | null;
  }[];
  base_dias: string;
  base_egresos: string;
  base_sitios: string;
  depositos: string[];
  descuadre_contra_snapshot: {
    filas_declaradas: number;
    declarado_usd: number | null;
    contable_usd: number;
    diferencia_usd?: number;
    nota?: string;
  };
}

export interface Deposito {
  ubicacion: string;
  tipo_ubicacion: string;
  capacidad_tn: number | null;
  stock_maximo_tn: number | null;
  ocupacion_pico_pct: number | null;
  productos: number;
  costo_almacenaje_usd: number | null;
}

export interface FlujoDeposito {
  run_id: string;
  ubicacion: string;
  dias_de_la_corrida: number;
  flujo: {
    ingresos_tn: number | null;
    ingresos_tn_en_arcos: number | null;
    arcos_de_ingreso: number;
    stock_promedio_tn: number | null;
    stock_maximo_tn: number | null;
    capacidad_tn: number | null;
    ocupacion_pico_pct: number | null;
    lotes_abiertos_pico: number | null;
    egresos_tn: number | null;
    arcos_de_egreso: number;
    dias_promedio_deposito: number | null;
    base_egresos: string;
  };
  costo: {
    costo_ingreso_usd: number | null;
    costo_almacenaje_usd: number | null;
    costo_egreso_usd: number | null;
    costo_total_usd: number | null;
  };
  decision: {
    evaluaciones: number;
    orden_ranking_promedio: number | null;
    elegida: number;
    no_factible: number;
    mas_barata_no_factible: number;
    toneladas_tomadas: number | null;
    motivos_de_descarte: { codigo_motivo: string; veces: number }[];
    base_ranking: string;
  };
  productos: {
    producto: string;
    stock_promedio_tn: number | null;
    stock_maximo_tn: number | null;
    ingresos_tn: number | null;
  }[];
}

export interface StockDiario {
  run_id: string;
  ubicacion: string;
  productos: string[];
  dias: number;
  /** ADR-064.2 (MOD v4.1): false en una corrida importada con un esquema anterior. */
  tiene_fecha_calendario: boolean;
  serie_diaria: {
    dia: number;
    fecha: string | null;
    producto: string;
    stock_fisico_tn: number | null;
    ocupacion_pct: number | null;
  }[];
}

export interface TopLotes {
  run_id: string;
  orden: string;
  lotes: {
    id_lote: string;
    producto: string;
    sitio: string;
    costo_almacenaje_usd: number | null;
    dias_con_cargo: number;
    dia_primer_cargo: number | null;
    dia_ultimo_cargo: number | null;
    toneladas: number | null;
    usd_por_tn: number | null;
  }[];
  base_toneladas: string;
}

export interface RecorridoLote {
  run_id: string;
  id_lote: string;
  producto: string | null;
  sitio: string | null;
  dia_ingreso: number | null;
  toneladas_ingresadas: number | null;
  toneladas_retiradas: number | null;
  toneladas_sin_retirar: number | null;
  costo_almacenaje_usd: number | null;
  dias_con_cargo_de_almacenaje: number;
  dia_primer_cargo: number | null;
  dia_ultimo_cargo: number | null;
  toneladas_facturadas: number | null;
  costo_por_categoria: {
    categoria: string;
    importe_usd: number | null;
    eventos: number;
    etapa: string | null;
  }[];
  costo_total_usd: number | null;
  recorrido: {
    dia_inicio: number | null;
    dia_fin: number | null;
    tipo_arco: string;
    origen: string;
    destino: string;
    toneladas: number | null;
    producto: string;
    id_contenedor: string;
    codigo_pedido: string;
    estado_final: string;
  }[];
  nota_recorrido: string;
}

const rutaCorrida = (runId: string, recurso: string, filtros: Record<string, string> = {}) => {
  const query = new URLSearchParams(filtros).toString();
  return `/simulation-runs/${encodeURIComponent(runId)}/${recurso}${query ? `?${query}` : ""}`;
};

export const traerCintas = (runId: string, filtros: Record<string, string>) =>
  pedir<Cintas>(rutaCorrida(runId, "costs/cintas/", filtros));

export const traerAlmacenajePorProducto = (runId: string, filtros: Record<string, string>) =>
  pedir<AlmacenajePorProducto>(rutaCorrida(runId, "almacenamiento/por-producto/", filtros));

export const traerDepositos = (runId: string) =>
  pedir<{ run_id: string; depositos: Deposito[] }>(rutaCorrida(runId, "almacenamiento/depositos/"));

export const traerFlujoDeposito = (runId: string, ubicacion: string) =>
  pedir<FlujoDeposito>(
    rutaCorrida(runId, `depositos/${encodeURIComponent(ubicacion)}/flujo-y-decision/`),
  );

export const traerStockDiario = (runId: string, ubicacion: string) =>
  pedir<StockDiario>(rutaCorrida(runId, `depositos/${encodeURIComponent(ubicacion)}/stock-diario/`));

export const traerTopLotes = (runId: string, filtros: Record<string, string>) =>
  pedir<TopLotes>(rutaCorrida(runId, "almacenamiento/top-lotes/", filtros));

export const traerRecorridoLote = (runId: string, idLote: string) =>
  pedir<RecorridoLote>(rutaCorrida(runId, `lotes/${encodeURIComponent(idLote)}/recorrido/`));
