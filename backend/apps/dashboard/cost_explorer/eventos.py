"""Eventos contables paginados: el ultimo nivel del drill-down.

El paquete real trae 106.365 cargos, asi que la lista siempre viene paginada y ordenada por una
lista blanca de columnas. Nunca se serializan todas las filas de una corrida: para llevarse el
detalle completo esta la exportacion CSV, que va por streaming.
"""

from __future__ import annotations

from apps.core.models import SimulationRun

from .agregados import cargos_filtrados
from .clasificacion import clasificar_etapa, tipo_geografia
from .filtros import FiltrosCostos

LIMITE_POR_DEFECTO = 100
LIMITE_MAXIMO = 500

ORDENES = {
    "importe": "-importe_usd",
    "dia": "dia",
    "dia_desc": "-dia",
    "categoria": "categoria",
}

CAMPOS = (
    "id_costo",
    "dia",
    "dia_campania",
    "tipo_contable",
    "categoria",
    "codigo_pedido",
    "id_asignacion",
    "id_decision",
    "id_contenedor",
    "id_lote",
    "producto",
    "circuito",
    "origen",
    "destino",
    "sitio",
    "unidad",
    "cantidad",
    "tarifa",
    "importe_usd",
    "alcance",
    "es_incremental",
    "motivo",
)


class PaginacionInvalida(ValueError):
    """El limite, el corrimiento o el orden pedido no sirven."""


def _entero(nombre: str, valor: str | None, por_defecto: int) -> int:
    if valor in (None, ""):
        return por_defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise PaginacionInvalida(f"{nombre} tiene que ser un entero, llego {valor!r}") from exc
    if numero < 0:
        raise PaginacionInvalida(f"{nombre} no puede ser negativo")
    return numero


def eventos(run: SimulationRun, filtros: FiltrosCostos, params) -> dict:
    limite = _entero("limit", params.get("limit"), LIMITE_POR_DEFECTO)
    corrimiento = _entero("offset", params.get("offset"), 0)
    if limite > LIMITE_MAXIMO:
        raise PaginacionInvalida(
            f"limit maximo {LIMITE_MAXIMO}; para el detalle completo usar la exportacion CSV"
        )

    orden = (params.get("orden") or "importe").strip()
    if orden not in ORDENES:
        raise PaginacionInvalida(
            f"orden desconocido {orden!r}; opciones: {', '.join(sorted(ORDENES))}"
        )

    cargos = cargos_filtrados(run, filtros)
    total = cargos.count()
    filas = list(
        cargos.order_by(ORDENES[orden], "id")
        .values(*CAMPOS)[corrimiento : corrimiento + limite]
    )
    for fila in filas:
        fila["etapa"] = clasificar_etapa(
            fila["categoria"], fila["alcance"], fila["origen"], fila["destino"]
        )
        fila["geografia"] = tipo_geografia(fila["origen"], fila["destino"])

    return {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "filtros_aplicados": filtros.como_dict(),
        "orden": orden,
        "limit": limite,
        "offset": corrimiento,
        "total": total,
        "filas": filas,
        "filas_consideradas": total,
    }
