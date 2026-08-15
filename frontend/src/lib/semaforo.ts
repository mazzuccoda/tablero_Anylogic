/**
 * Estado (semaforo) de los indicadores de nivel 0 y 1 (MOD v4.0).
 *
 * Los umbrales de abajo NO vienen de AnyLogic ni de ninguna regla de negocio declarada: son una
 * primera configuracion para que el semaforo tenga algun criterio en vez de ninguno. Se pueden
 * ajustar cuando haya una referencia real (un objetivo de servicio, un tope de sobrecosto
 * aceptado, etc.) - por eso viven todos juntos en este archivo y no repartidos por la UI.
 */

export type Estado = "ok" | "atencion" | "critico" | "sin_dato";

const ORDEN_GRAVEDAD: Estado[] = ["critico", "atencion", "sin_dato", "ok"];

/** El peor estado de la lista manda: un KPI en rojo pesa mas que diez en verde. */
export function peorEstado(estados: Estado[]): Estado {
  for (const nivel of ORDEN_GRAVEDAD) {
    if (estados.includes(nivel)) return nivel;
  }
  return "sin_dato";
}

export function estadoServicio(nivelServicio: number | null | undefined): Estado {
  if (nivelServicio === null || nivelServicio === undefined) return "sin_dato";
  if (nivelServicio >= 0.9) return "ok";
  if (nivelServicio >= 0.8) return "atencion";
  return "critico";
}

export function estadoRestriccion(masBaratasNoFactibles: number | null | undefined): Estado {
  if (masBaratasNoFactibles === null || masBaratasNoFactibles === undefined) return "sin_dato";
  if (masBaratasNoFactibles === 0) return "ok";
  if (masBaratasNoFactibles <= 10) return "atencion";
  return "critico";
}

export function estadoCapacidad(usoPicoPct: number | null | undefined): Estado {
  if (usoPicoPct === null || usoPicoPct === undefined) return "sin_dato";
  if (usoPicoPct < 80) return "ok";
  if (usoPicoPct < 100) return "atencion";
  return "critico";
}

/** Variacion porcentual (0-100) de un costo vs. la corrida anterior del mismo escenario. */
export function estadoCosto(variacionPct: number | null | undefined): Estado {
  if (variacionPct === null || variacionPct === undefined) return "sin_dato";
  if (variacionPct <= 0) return "ok";
  if (variacionPct <= 10) return "atencion";
  return "critico";
}

export const ETIQUETA_ESTADO: Record<Estado, string> = {
  ok: "en rango",
  atencion: "atención",
  critico: "crítico",
  sin_dato: "sin dato",
};

export const COLOR_ESTADO: Record<Estado, string> = {
  ok: "#15803d",
  atencion: "#b45309",
  critico: "#b91c1c",
  sin_dato: "#94a3b8",
};
