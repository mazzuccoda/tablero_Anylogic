"""Objetos de costo y sus toneladas (MOD v3.2, seccion B).

El USD/tn no se puede calcular dividiendo el importe por la suma de `cantidad`: en el paquete real
`cantidad` viene en `USD_TN_DIA` (toneladas-dia de almacenamiento), `USD_CONTENEDOR`, `USD_TN` y
`USD_VIAJE`, y sumar esas cuatro cosas no significa nada. El denominador sale del objeto de costo:

- LOTE: toneladas ingresadas, que estan en `ejecucion_arcos` (`PLANTA_DEPOSITO` y `CROSS_DOCK`) y
  tambien en la `cantidad` del cargo `IN_DEPOSITO`; en el paquete real las dos fuentes coinciden en
  los 145 lotes, asi que se usa el arco (dato fisico) y el cargo queda como respaldo;
- CONTENEDOR: toneladas cargadas en el arco `CARGA_CONSOLIDACION`;
- PEDIDO: `toneladas_entregadas` de `asignaciones_elegidas`.

Un objeto sin fuente de toneladas queda en `None`: su USD/tn se muestra "sin dato". Nunca cero.
"""

from __future__ import annotations

from django.db.models import Count, Sum

from apps.core.models import ArcExecution, AssignmentResult, CostCharge, SimulationRun, TipoContable

ARCOS_INGRESO_LOTE = ("PLANTA_DEPOSITO", "CROSS_DOCK")
ARCO_CARGA_CONTENEDOR = "CARGA_CONSOLIDACION"
CATEGORIA_INGRESO = "IN_DEPOSITO"

BASE_TN_ENTREGADAS = "tn_entregadas"
BASE_CONTENEDORES_ENTREGADOS = "contenedores_entregados"
BASE_PEDIDOS_CON_ENTREGA = "pedidos_con_entrega"


def _por_clave(queryset, clave: str, campo: str) -> dict[str, float]:
    filas = (
        queryset.exclude(**{f"{clave}__exact": ""})
        .values(clave)
        .annotate(total=Sum(campo))
        .order_by()
    )
    return {fila[clave]: fila["total"] for fila in filas if fila["total"] is not None}


def toneladas_por_lote(run: SimulationRun) -> dict[str, float]:
    """Toneladas ingresadas por lote, con el cargo `IN_DEPOSITO` como respaldo del arco."""
    toneladas = _por_clave(
        ArcExecution.objects.filter(simulation_run=run, tipo_arco__in=ARCOS_INGRESO_LOTE),
        "id_lote",
        "toneladas",
    )
    respaldo = _por_clave(
        CostCharge.objects.filter(simulation_run=run, categoria=CATEGORIA_INGRESO, unidad="USD_TN"),
        "id_lote",
        "cantidad",
    )
    for lote, tn in respaldo.items():
        toneladas.setdefault(lote, tn)
    return toneladas


def toneladas_por_contenedor(run: SimulationRun) -> dict[str, float]:
    return _por_clave(
        ArcExecution.objects.filter(simulation_run=run, tipo_arco=ARCO_CARGA_CONTENEDOR),
        "id_contenedor",
        "toneladas",
    )


def toneladas_por_pedido(run: SimulationRun) -> dict[str, float]:
    return _por_clave(
        AssignmentResult.objects.filter(simulation_run=run),
        "codigo_pedido",
        "toneladas_entregadas",
    )


def bases_de_la_red(run: SimulationRun) -> dict[str, float | None]:
    """Denominadores de red: son los que usan las tarjetas de portada."""
    resumen = AssignmentResult.objects.filter(simulation_run=run).aggregate(
        toneladas=Sum("toneladas_entregadas"),
        contenedores=Sum("contenedores_entregados"),
    )
    pedidos = (
        AssignmentResult.objects.filter(simulation_run=run, toneladas_entregadas__gt=0)
        .exclude(codigo_pedido__exact="")
        .aggregate(pedidos=Count("codigo_pedido", distinct=True))["pedidos"]
    )
    return {
        BASE_TN_ENTREGADAS: resumen["toneladas"],
        BASE_CONTENEDORES_ENTREGADOS: resumen["contenedores"],
        BASE_PEDIDOS_CON_ENTREGA: pedidos or None,
    }


def toneladas_entregadas(run: SimulationRun) -> float | None:
    return bases_de_la_red(run)[BASE_TN_ENTREGADAS]


def metrica(importe: float | None, base_nombre: str, base_valor: float | None) -> dict:
    """Arma un ratio con su base declarada.

    Ningun `usd_*` se publica sin decir sobre que se dividio: cada etapa tiene su propia base
    fisica (toneladas ingresadas, toneladas en contenedor, contenedores) y sin la base el numero no
    se puede comparar ni reproducir.
    """
    valor = None
    if importe is not None and base_valor:
        valor = importe / base_valor
    return {"valor": valor, "base": {"nombre": base_nombre, "valor": base_valor}}


def costo_por_objeto(
    run: SimulationRun,
    filtros,
    clave: str,
) -> list[dict]:
    """Importe y USD/tn por objeto de costo (`id_lote`, `id_contenedor` o `codigo_pedido`)."""
    toneladas = {
        "id_lote": toneladas_por_lote,
        "id_contenedor": toneladas_por_contenedor,
        "codigo_pedido": toneladas_por_pedido,
    }[clave](run)

    cargos = filtros.aplicar(CostCharge.objects.filter(simulation_run=run))
    filas = (
        cargos.exclude(**{f"{clave}__exact": ""})
        .values(clave)
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
        .order_by("-importe_usd")
    )

    salida = []
    for fila in filas:
        identificador = fila[clave]
        tn = toneladas.get(identificador)
        salida.append(
            {
                clave: identificador,
                "importe_usd": fila["importe_usd"],
                "eventos": fila["eventos"],
                "toneladas": tn,
                "usd_por_tn": (fila["importe_usd"] / tn) if tn and fila["importe_usd"] else None,
            }
        )
    return salida


def cargos_caja(run: SimulationRun):
    return CostCharge.objects.filter(simulation_run=run, tipo_contable=TipoContable.CAJA)
