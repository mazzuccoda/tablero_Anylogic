"""Agrupacion de series por dia, semana, mes o anio (MOD v4.1, ADR-064.2).

`fecha` llega desde ADR-064.2: un paquete importado con un esquema anterior no la trae, y agrupar
por semana/mes/anio sin fecha no significa nada (no hay calendario), asi que quien llama esta
funcion tiene que decidir por si mismo si cae a "dia" en ese caso - este modulo no lo hace en
silencio.

`semana` usa el lunes de esa semana (ISO) como fecha de referencia, no el numero de semana: evita
la ambiguedad de la "semana 53" en los bordes de anio y ordena tal cual por fecha.
"""

from __future__ import annotations

from datetime import date, timedelta

AGRUPACIONES = ("dia", "semana", "mes", "anio")


class AgrupacionInvalida(ValueError):
    """`agrupar_por` no es una de las agrupaciones que este modulo entiende."""


def periodo_de(fecha_dia: date, agrupar_por: str) -> tuple[str, date]:
    """(etiqueta del periodo, fecha de referencia para ordenar periodos) de `fecha_dia`."""
    if agrupar_por == "semana":
        lunes = fecha_dia - timedelta(days=fecha_dia.weekday())
        return lunes.isoformat(), lunes
    if agrupar_por == "mes":
        primero = fecha_dia.replace(day=1)
        return primero.isoformat()[:7], primero
    if agrupar_por == "anio":
        return str(fecha_dia.year), date(fecha_dia.year, 1, 1)
    return fecha_dia.isoformat(), fecha_dia


def agrupar_por_periodo(
    filas: list[dict],
    agrupar_por: str,
    *,
    campo_fecha: str,
    campo_dia: str,
    campos_nivel: tuple[str, ...] = (),
    campos_flujo: tuple[str, ...] = (),
) -> list[dict]:
    """Agrupa una serie ya resuelta por dia (lista de dicts) en periodos mas anchos.

    `campos_nivel` son magnitudes de nivel en un momento dado (stock, ocupacion): sumarlas entre
    varios dias daria una unidad distinta (toneladas-dia en vez de toneladas), asi que el periodo
    se resume con el promedio de sus dias (y el pico, en `<campo>_pico`).
    `campos_flujo` son magnitudes que si se acumulan en el tiempo (costo, toneladas movidas): esas
    si se suman entre los dias del periodo.

    Si `agrupar_por == "dia"` (o no es una agrupacion conocida) devuelve una fila por dia, con la
    misma forma que las agrupadas, para que el consumidor no tenga que distinguir los dos casos.
    """
    if agrupar_por not in AGRUPACIONES:
        raise AgrupacionInvalida(
            f"agrupar_por desconocido {agrupar_por!r}; opciones: {', '.join(AGRUPACIONES)}"
        )

    if agrupar_por == "dia":
        salida = []
        for f in filas:
            fecha_dia = f.get(campo_fecha)
            entrada = {
                "periodo": fecha_dia.isoformat() if fecha_dia else str(f[campo_dia]),
                "dia_desde": f[campo_dia],
                "dia_hasta": f[campo_dia],
                "fecha_desde": fecha_dia.isoformat() if fecha_dia else None,
                "fecha_hasta": fecha_dia.isoformat() if fecha_dia else None,
                "dias": 1,
            }
            for campo in campos_nivel:
                entrada[campo] = f.get(campo)
                entrada[f"{campo}_pico"] = f.get(campo)
            for campo in campos_flujo:
                entrada[campo] = f.get(campo)
            salida.append(entrada)
        return salida

    baldes: dict[str, list[dict]] = {}
    referencia: dict[str, date] = {}
    sin_fecha = 0
    for f in filas:
        fecha_dia = f.get(campo_fecha)
        if fecha_dia is None:
            sin_fecha += 1
            continue
        etiqueta, ref = periodo_de(fecha_dia, agrupar_por)
        baldes.setdefault(etiqueta, []).append(f)
        referencia[etiqueta] = ref

    salida = []
    for etiqueta in sorted(baldes, key=lambda e: referencia[e]):
        grupo = baldes[etiqueta]
        dias = sorted(f[campo_dia] for f in grupo)
        fechas = sorted(f[campo_fecha] for f in grupo)
        entrada = {
            "periodo": etiqueta,
            "dia_desde": dias[0],
            "dia_hasta": dias[-1],
            "fecha_desde": fechas[0].isoformat(),
            "fecha_hasta": fechas[-1].isoformat(),
            "dias": len(grupo),
        }
        for campo in campos_nivel:
            valores = [f[campo] for f in grupo if f.get(campo) is not None]
            entrada[campo] = sum(valores) / len(valores) if valores else None
            entrada[f"{campo}_pico"] = max(valores) if valores else None
        for campo in campos_flujo:
            valores = [f[campo] for f in grupo if f.get(campo) is not None]
            entrada[campo] = sum(valores) if valores else None
        salida.append(entrada)

    if sin_fecha:
        # No se descarta en silencio: si esto pasa es porque la corrida mezcla filas con fecha y
        # sin fecha, algo que hoy no deberia ocurrir (la fecha se deriva del mismo dia_campania
        # para todas), asi que vale la pena que se note en vez de perderse.
        salida.append(
            {
                "periodo": "SIN_FECHA",
                "dia_desde": None,
                "dia_hasta": None,
                "fecha_desde": None,
                "fecha_hasta": None,
                "dias": sin_fecha,
                **{c: None for c in campos_nivel + campos_flujo},
            }
        )
    return salida
