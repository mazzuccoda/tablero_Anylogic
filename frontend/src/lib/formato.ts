const NUMERO = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });
const ENTERO = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const FORMATO_FECHA = new Intl.DateTimeFormat("es-AR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

/** Un vacio del modelo se muestra como "sin dato", nunca como 0 (ADR-064 seccion 5). */
export const SIN_DATO = "sin dato";

export function numero(valor: number | null | undefined, decimales = 2): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  return decimales === 0 ? ENTERO.format(valor) : NUMERO.format(valor);
}

export function usd(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  return `USD ${NUMERO.format(valor)}`;
}

export function porcentaje(valor: number | null | undefined, base1 = false): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  return `${NUMERO.format(base1 ? valor * 100 : valor)} %`;
}

export function booleano(valor: boolean | null | undefined): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  return valor ? "si" : "no";
}

export function horas(valor: number | null | undefined, aplica = true): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  if (!aplica || valor < 0) return "no aplica";
  return `${NUMERO.format(valor)} h`;
}

/** `fecha_inicio_campania` (ADR-064.2): "YYYY-MM-DD" -> "01 abr 2026". null en corridas
 * importadas con un esquema anterior, que no la traen. */
export function fecha(valor: string | null | undefined): string {
  if (!valor) return SIN_DATO;
  const parseada = new Date(`${valor}T00:00:00`);
  if (Number.isNaN(parseada.getTime())) return valor;
  return FORMATO_FECHA.format(parseada);
}
