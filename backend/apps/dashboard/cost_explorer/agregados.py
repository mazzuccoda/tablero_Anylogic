"""Agregados del Cost Explorer.

Todo se agrega en la base (`values().annotate()`), nunca en Python: el paquete real trae 105.270
cargos de caja y traerlos a memoria para sumarlos seria el unico N+1 que importa. Lo que si se hace
en Python es plegar categoria en etapa, porque la etapa no es una columna sino una clasificacion, y
son diez claves.
"""

from __future__ import annotations

from django.db.models import Count, Sum

from apps.core.models import CostCharge, SimulationRun, TipoContable

from .clasificacion import ETAPA_NO_CLASIFICADA, clasificar_etapa, ordenar_por_etapa
from .filtros import FiltrosCostos
from .objetos import (
    BASE_CONTENEDORES_ENTREGADOS,
    BASE_PEDIDOS_CON_ENTREGA,
    BASE_TN_ENTREGADAS,
    bases_de_la_red,
    metrica,
)


def cargos_filtrados(run: SimulationRun, filtros: FiltrosCostos):
    return filtros.aplicar(CostCharge.objects.filter(simulation_run=run))


def _agrupar(run: SimulationRun, filtros: FiltrosCostos, campo: str) -> list[dict]:
    return list(
        cargos_filtrados(run, filtros)
        .values(campo)
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
        .order_by("-importe_usd")
    )


def _porcentaje(importe: float | None, total: float | None) -> float | None:
    if importe is None or not total:
        return None
    return importe / total * 100


def _etiquetar_sin_dato(filas: list[dict], campo: str) -> list[dict]:
    """Un vacio se publica como `SIN_CLASIFICAR`, no se descarta.

    Descartarlo rompería la reconciliacion sin avisar: el total dejaria de ser la suma del desglose.
    """
    for fila in filas:
        if not fila[campo]:
            fila[campo] = "SIN_CLASIFICAR"
    return filas


def costos_por_categoria(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    total = total_filtrado(run, filtros)
    filas = _etiquetar_sin_dato(_agrupar(run, filtros, "categoria"), "categoria")
    for fila in filas:
        fila["etapa"] = clasificar_etapa(fila["categoria"])
        fila["porcentaje"] = _porcentaje(fila["importe_usd"], total)
    return filas


def costos_por_etapa(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Pliega categoria en etapa conservando de que categorias vino cada etapa."""
    total = total_filtrado(run, filtros)
    por_etapa: dict[str, dict] = {}
    for fila in _agrupar(run, filtros, "categoria"):
        etapa = clasificar_etapa(fila["categoria"])
        acumulado = por_etapa.setdefault(
            etapa, {"etapa": etapa, "importe_usd": 0.0, "eventos": 0, "categorias": []}
        )
        acumulado["importe_usd"] += fila["importe_usd"] or 0.0
        acumulado["eventos"] += fila["eventos"]
        if fila["categoria"]:
            acumulado["categorias"].append(fila["categoria"])

    filas = ordenar_por_etapa(list(por_etapa.values()))
    for fila in filas:
        fila["categorias"] = sorted(fila["categorias"])
        fila["porcentaje"] = _porcentaje(fila["importe_usd"], total)
    return filas


def total_filtrado(run: SimulationRun, filtros: FiltrosCostos) -> float | None:
    return cargos_filtrados(run, filtros).aggregate(total=Sum("importe_usd"))["total"]


def _contraparte(run: SimulationRun, filtros: FiltrosCostos) -> dict:
    """El otro tipo contable, con el mismo recorte y siempre separado.

    `CAJA` y `ECONOMICO` no se suman (ADR-T04): el economico es costo de oportunidad. Se informa al
    lado para que se vea que existe, no para que se agregue al total.
    """
    otro = (
        TipoContable.ECONOMICO
        if filtros.tipo_contable == TipoContable.CAJA
        else TipoContable.CAJA
    )
    espejo = FiltrosCostos(
        tipo_contable=otro,
        exactos=dict(filtros.exactos),
        etapa=filtros.etapa,
        dia_desde=filtros.dia_desde,
        dia_hasta=filtros.dia_hasta,
    )
    resumen = cargos_filtrados(run, espejo).aggregate(total=Sum("importe_usd"), eventos=Count("id"))
    return {
        "tipo_contable": otro,
        "importe_usd": resumen["total"],
        "eventos": resumen["eventos"],
    }


def _top(filas: list[dict], campo: str) -> dict | None:
    return filas[0] if filas else None


def resumen_costos(run: SimulationRun, filtros: FiltrosCostos) -> dict:
    """Tarjetas de portada del Cost Explorer.

    Cada ratio viaja con su base: el USD/tn de la red se divide por toneladas entregadas, y no es la
    suma de los USD/tn por etapa (cada etapa tiene otra base fisica). El waterfall se hace en USD.
    """
    cargos = cargos_filtrados(run, filtros)
    resumen = cargos.aggregate(importe=Sum("importe_usd"), eventos=Count("id"))
    total = resumen["importe"]
    bases = bases_de_la_red(run)

    etapas = costos_por_etapa(run, filtros)
    circuitos = _etiquetar_sin_dato(_agrupar(run, filtros, "circuito"), "circuito")
    productos = _etiquetar_sin_dato(_agrupar(run, filtros, "producto"), "producto")

    sin_clasificar = next(
        (f["importe_usd"] for f in etapas if f["etapa"] == ETAPA_NO_CLASIFICADA), 0.0
    )

    return {
        "run_id": run.run_id,
        "escenario": run.scenario.codigo,
        "replica": run.replica,
        "tipo_contable": filtros.tipo_contable,
        "importe_usd": total,
        "eventos": resumen["eventos"],
        "contraparte": _contraparte(run, filtros),
        "usd_por_tn": metrica(total, BASE_TN_ENTREGADAS, bases[BASE_TN_ENTREGADAS]),
        "usd_por_contenedor": metrica(
            total, BASE_CONTENEDORES_ENTREGADOS, bases[BASE_CONTENEDORES_ENTREGADOS]
        ),
        "usd_por_pedido": metrica(
            total, BASE_PEDIDOS_CON_ENTREGA, bases[BASE_PEDIDOS_CON_ENTREGA]
        ),
        "etapa_principal": _top(
            sorted(etapas, key=lambda f: -(f["importe_usd"] or 0.0)), "etapa"
        ),
        "circuito_mas_caro": _top(circuitos, "circuito"),
        "producto_mas_caro": _top(productos, "producto"),
        "etapa_no_clasificada_usd": sin_clasificar,
        "filtros_aplicados": filtros.como_dict(),
        "filas_consideradas": resumen["eventos"],
        "importe_considerado": total,
    }
