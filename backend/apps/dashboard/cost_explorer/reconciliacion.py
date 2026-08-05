"""Reconciliacion por dimension (MOD v3.2, seccion B.4).

No hay un unico `estado: OK | WARNING`. En el paquete real hay dos clases de dimension:

- las que estan poblados en el 100 % del importe (categoria, etapa, producto, circuito, origen,
  destino, sitio, alcance, unidad): ahi el desglose tiene que dar **exacto** y una diferencia
  distinta de cero es un bug de esta plataforma, no un dato faltante;
- las que no (pedido, asignacion, contenedor): el 45,9 % del costo de caja se devenga por lote y no
  trae `codigo_pedido`, asi que el desglose por pedido es **parcial por definicion** y hay que
  decirlo con el importe que queda afuera. Fingir que reconcilia metiendo el 46 % en
  `SIN_CLASIFICAR` haria que el USD/pedido de la portada mienta.
"""

from __future__ import annotations

from django.db.models import Count, Q, Sum

from apps.core.models import SimulationRun

from .agregados import cargos_filtrados, costos_por_etapa, total_filtrado
from .filtros import FiltrosCostos

EXACTA = "EXACTA"
PARCIAL = "PARCIAL"
DESCUADRADA = "DESCUADRADA"

# Dimensiones que el contrato ADR-064 escribe en toda fila de `costos_eventos`.
DIMENSIONES_COMPLETAS = (
    "categoria",
    "producto",
    "circuito",
    "origen",
    "destino",
    "sitio",
    "alcance",
)

# Dimensiones que solo existen en algunos cargos, con el motivo por el que faltan.
DIMENSIONES_PARCIALES = {
    "codigo_pedido": "el costo que se devenga por lote (almacenamiento, ingreso, flete a deposito) "
    "no trae pedido: se atribuye por toneladas retiradas, no por prorrateo",
    "id_asignacion": "solo los cargos de contenedor cuelgan de una asignacion",
    "id_contenedor": "solo los cargos posteriores a la consolidacion tienen contenedor",
}

TOLERANCIA_USD = 0.01


def _suma_por(run: SimulationRun, filtros: FiltrosCostos, campo: str) -> dict:
    resumen = cargos_filtrados(run, filtros).aggregate(
        suma=Sum("importe_usd"),
        con_dato=Sum("importe_usd", filter=~Q(**{f"{campo}__exact": ""})),
        filas_con_dato=Count("id", filter=~Q(**{f"{campo}__exact": ""})),
        valores=Count(campo, distinct=True),
    )
    return resumen


def reconciliar_costos(run: SimulationRun, filtros: FiltrosCostos) -> dict:
    """Compara el total con la suma de cada desglose y declara el estado por dimension."""
    total = total_filtrado(run, filtros) or 0.0
    dimensiones: dict[str, dict] = {}

    etapas = costos_por_etapa(run, filtros)
    suma_etapas = sum(fila["importe_usd"] or 0.0 for fila in etapas)
    dimensiones["etapa"] = {
        "suma": suma_etapas,
        "diferencia": total - suma_etapas,
        "estado": EXACTA if abs(total - suma_etapas) <= TOLERANCIA_USD else DESCUADRADA,
        "valores": len(etapas),
    }

    for campo in DIMENSIONES_COMPLETAS:
        resumen = _suma_por(run, filtros, campo)
        suma = resumen["suma"] or 0.0
        diferencia = total - suma
        dimensiones[campo] = {
            "suma": suma,
            "diferencia": diferencia,
            "estado": EXACTA if abs(diferencia) <= TOLERANCIA_USD else DESCUADRADA,
            "valores": resumen["valores"],
            "importe_sin_dato": suma - (resumen["con_dato"] or 0.0),
        }

    for campo, motivo in DIMENSIONES_PARCIALES.items():
        resumen = _suma_por(run, filtros, campo)
        con_dato = resumen["con_dato"] or 0.0
        diferencia = total - con_dato
        dimensiones[campo] = {
            "suma": con_dato,
            "diferencia": diferencia,
            "estado": PARCIAL if abs(diferencia) > TOLERANCIA_USD else EXACTA,
            "valores": resumen["valores"],
            "filas_con_dato": resumen["filas_con_dato"],
            "motivo": motivo if abs(diferencia) > TOLERANCIA_USD else "",
        }

    descuadradas = sorted(
        campo for campo, fila in dimensiones.items() if fila["estado"] == DESCUADRADA
    )
    etapa_no_clasificada = next(
        (f["importe_usd"] for f in etapas if f["etapa"] == "ETAPA_NO_CLASIFICADA"), 0.0
    )

    return {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "total_usd": total,
        "dimensiones": dimensiones,
        "dimensiones_descuadradas": descuadradas,
        "etapa_no_clasificada_usd": etapa_no_clasificada,
        "categorias_sin_clasificar": categorias_sin_clasificar(run, filtros),
        "filtros_aplicados": filtros.como_dict(),
    }


def categorias_sin_clasificar(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Categorias que el mapa de etapas no conoce.

    Es la señal de que el modelo de AnyLogic empezo a escribir un costo nuevo. Aparece en la API y
    rompe una prueba: si cayera en un cajon "OTROS" nadie se enteraria.
    """
    from .clasificacion import ETAPA_POR_CATEGORIA

    filas = (
        cargos_filtrados(run, filtros)
        .exclude(categoria__in=sorted(ETAPA_POR_CATEGORIA))
        .values("categoria")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
        .order_by("-importe_usd")
    )
    return list(filas)
