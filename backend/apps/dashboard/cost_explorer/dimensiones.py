"""Desgloses por dimension y waterfall.

Las dimensiones que se pueden pedir son una lista blanca: son las columnas que `costos_eventos`
escribe en toda fila, asi que cada desglose reconcilia con el total. `origen`/`destino` se publican
juntos como arco, separando el auto-loop (costo de nodo) del tramo real, porque en el paquete real
los pares mas frecuentes son `RUTA9 -> RUTA9` y mezclarlos deja el ranking de arcos dominado por el
deposito.
"""

from __future__ import annotations

from django.db.models import Count, Sum

from apps.core.models import SimulationRun

from .agregados import (
    _agrupar,
    _etiquetar_sin_dato,
    _porcentaje,
    cargos_filtrados,
    costos_por_etapa,
    total_filtrado,
)
from .clasificacion import ARCO, NODO, tipo_geografia
from .filtros import FiltrosCostos

DIMENSIONES = (
    "producto",
    "material",
    "circuito",
    "sitio",
    "origen",
    "destino",
    "alcance",
    "unidad",
    "motivo",
)


class DimensionInvalida(ValueError):
    """La dimension pedida no esta en la lista blanca."""


def costos_por_dimension(run: SimulationRun, filtros: FiltrosCostos, campo: str) -> list[dict]:
    if campo not in DIMENSIONES:
        raise DimensionInvalida(
            f"dimension desconocida {campo!r}; opciones: {', '.join(DIMENSIONES)}"
        )
    total = total_filtrado(run, filtros)
    filas = _etiquetar_sin_dato(_agrupar(run, filtros, campo), campo)
    for fila in filas:
        fila["porcentaje"] = _porcentaje(fila["importe_usd"], total)
    return filas


def costos_por_arco(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Costo por par origen-destino, diciendo si es un nodo o un tramo."""
    total = total_filtrado(run, filtros)
    filas = _costos_por_par(run, filtros)
    for fila in filas:
        fila["tipo"] = tipo_geografia(fila["origen"], fila["destino"])
        fila["porcentaje"] = _porcentaje(fila["importe_usd"], total)
    return filas


def _costos_por_par(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    return list(
        cargos_filtrados(run, filtros)
        .values("origen", "destino")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
        .order_by("-importe_usd")
    )


def resumen_nodo_arco(filas: list[dict]) -> dict:
    """Cuanto del costo se paga estando quieto y cuanto moviendose."""
    totales = {NODO: 0.0, ARCO: 0.0}
    for fila in filas:
        if fila["tipo"] in totales:
            totales[fila["tipo"]] += fila["importe_usd"] or 0.0
    return {"nodo_usd": totales[NODO], "arco_usd": totales[ARCO]}


def waterfall(run: SimulationRun, filtros: FiltrosCostos) -> dict:
    """Etapas en orden logistico con el acumulado, para dibujar la cascada.

    `base` es lo acumulado antes de la etapa: el grafico apila una barra invisible de `base` y
    encima el `importe_usd`. El paso final es el total, que por construccion es la suma de los
    pasos y no un numero calculado aparte.
    """
    etapas = costos_por_etapa(run, filtros)
    pasos = []
    acumulado = 0.0
    for fila in etapas:
        importe = fila["importe_usd"] or 0.0
        pasos.append(
            {
                "etapa": fila["etapa"],
                "categorias": fila["categorias"],
                "importe_usd": fila["importe_usd"],
                "base": acumulado,
                "acumulado": acumulado + importe,
                "porcentaje": fila["porcentaje"],
                "eventos": fila["eventos"],
            }
        )
        acumulado += importe

    return {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "filtros_aplicados": filtros.como_dict(),
        "pasos": pasos,
        "total_usd": acumulado if pasos else None,
        "filas_consideradas": sum(paso["eventos"] for paso in pasos),
        "importe_considerado": acumulado if pasos else None,
    }
