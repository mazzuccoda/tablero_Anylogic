"""Almacenaje: por producto, por deposito (flujo + costo + decision) y trazabilidad de lote.

Cuatro cosas que se midieron contra el paquete real antes de escribir esto, porque cambian el
calculo respecto de lo que uno esperaria leyendo el esquema:

- **`egresos_dia_tn` viene en cero en los cinco depositos** (solo `PLANTA` lo escribe), pero el
  stock de esos depositos si baja. Los egresos se derivan de `ejecucion_arcos`: el retiro de un
  deposito es un `CARGA_CONSOLIDACION` con `origen` = ese deposito. `ingresos_dia_tn`, en cambio,
  coincide exacto con los arcos que entran, asi que ese se usa tal cual y sirve de control.
- **El costo de almacenaje solo existe para los productos que efectivamente se guardan.** En la
  corrida real son JUGO y CASCARA; ACEITE tiene stock en PLANTA y PLANTA no cobra almacenaje. Un
  producto sin cargo aparece con `costo_almacenaje_usd = null`, no con cero.
- **`snapshot_inventario` trae su propio `costo_almacenaje_dia_usd`** y no cierra exacto contra
  `costos_eventos` (1332429,42 contra 1346239,03 en E-00-R0, 1 %). La fuente de importes sigue
  siendo `costos_eventos` (ADR-T04) y el descuadre se publica en vez de taparse.
- **`origen_stock = DEPOSITO` no es un deposito**: son las 1443 filas del pseudo-motivo
  `TRANSFERENCIA_DEPOSITO_DEPOSITO`, con `orden_ranking = 0`. Se excluye del ranking de decisiones
  de un deposito concreto porque contaminaria el promedio.
"""

from __future__ import annotations

from django.db.models import Avg, Count, Max, Min, Q, Sum

from apps.core.models import (
    ArcExecution,
    CostCharge,
    DecisionAlternative,
    InventorySnapshot,
    SimulationRun,
    TipoContable,
)
from apps.dashboard.cost_explorer.clasificacion import ALMACENAMIENTO
from apps.dashboard.cost_explorer.filtros import FiltrosCostos

CATEGORIA_ALMACENAJE = "ALMACENAMIENTO"
CATEGORIAS_INGRESO = ("FLETE_PRODUCTO", "IN_DEPOSITO", "CROSS_DOCK")
CATEGORIAS_EGRESO = ("OUT_DEPOSITO", "CONSOLIDACION")
TIPOS_ARCO_INGRESO = ("PLANTA_DEPOSITO", "CROSS_DOCK", "DEPOSITO_DEPOSITO")
TIPOS_ARCO_EGRESO = ("CARGA_CONSOLIDACION",)
CAMPO_COSTO_DECLARADO = "costo_almacenaje_dia_usd"
PSEUDO_ORIGEN = "DEPOSITO"
TIPO_DEPOSITO = "DEPOSITO"


class OrdenInvalido(ValueError):
    """El orden pedido para el ranking de lotes no esta en la lista blanca."""


BASE_DIAS = (
    "dias promedio en deposito = (suma del stock fisico diario) / toneladas ingresadas "
    "(ley de Little); no es el promedio de dias_stock_promedio de AnyLogic"
)
BASE_EGRESOS = (
    "egresos = toneladas de los arcos CARGA_CONSOLIDACION que salen del sitio; "
    "egresos_dia_tn de snapshot_inventario viene en cero para los depositos"
)
BASE_SITIOS = (
    "la vista por producto mira solo los sitios tipo DEPOSITO: PLANTA tiene stock pero no cobra "
    "almacenaje, y mezclarla inflaria el stock promedio y los dias en deposito"
)


def _numero(valor: object) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def cargos_de_almacenaje(run: SimulationRun, filtros: FiltrosCostos):
    return filtros.aplicar(CostCharge.objects.filter(simulation_run=run)).filter(
        categoria=CATEGORIA_ALMACENAJE
    )


def _dias_de_la_corrida(run: SimulationRun) -> int:
    return InventorySnapshot.objects.filter(simulation_run=run).values("dia").distinct().count()


def _inventario_de_depositos(run: SimulationRun):
    return InventorySnapshot.objects.filter(simulation_run=run, tipo_ubicacion=TIPO_DEPOSITO)


def depositos(run: SimulationRun) -> list[dict]:
    """Sitios con stock, con lo justo para dibujar los chips del selector."""
    consulta = (
        InventorySnapshot.objects.filter(simulation_run=run)
        .values("ubicacion", "tipo_ubicacion")
        .annotate(
            capacidad_tn=Max("capacidad_tn"),
            stock_maximo_tn=Max("stock_fisico_tn"),
            ocupacion_pico_pct=Max("ocupacion_pct"),
            productos=Count("producto", distinct=True),
        )
        .order_by("ubicacion")
    )
    almacenaje = dict(
        CostCharge.objects.filter(simulation_run=run, tipo_contable=TipoContable.CAJA)
        .filter(categoria=CATEGORIA_ALMACENAJE)
        .values_list("sitio")
        .annotate(total=Sum("importe_usd"))
    )
    filas = []
    for fila in consulta:
        filas.append({**fila, "costo_almacenaje_usd": almacenaje.get(fila["ubicacion"])})
    return filas


def _ubicaciones_con_stock(run: SimulationRun) -> list[str]:
    return list(_inventario_de_depositos(run).values_list("ubicacion", flat=True).distinct())


def _stock_por_producto(run: SimulationRun) -> dict[str, dict]:
    """Stock y ingresos por producto, sumando los depositos.

    El maximo se calcula sobre el total diario de la red y no fila por fila: el pico de un producto
    es el dia en que mas habia guardado entre todos los depositos, no el mayor de un deposito.
    """
    fisico: dict[str, dict] = {}
    por_dia: dict[tuple[str, int], float] = {}
    consulta = (
        _inventario_de_depositos(run)
        .values("producto", "dia")
        .annotate(stock_tn=Sum("stock_fisico_tn"), ingresos_tn=Sum("ingresos_dia_tn"))
    )
    for fila in consulta:
        datos = fisico.setdefault(
            fila["producto"], {"stock_tn_dia": 0.0, "ingresos_tn": 0.0, "stock_maximo_tn": 0.0}
        )
        stock = fila["stock_tn"] or 0.0
        datos["stock_tn_dia"] += stock
        datos["ingresos_tn"] += fila["ingresos_tn"] or 0.0
        por_dia[(fila["producto"], fila["dia"])] = stock
    for (producto, _dia), stock in por_dia.items():
        fisico[producto]["stock_maximo_tn"] = max(fisico[producto]["stock_maximo_tn"], stock)
    return fisico


def por_producto(run: SimulationRun, filtros: FiltrosCostos) -> dict:
    """Ingresos, stock, egresos, dias en deposito y costo de almacenaje de cada producto."""
    dias = _dias_de_la_corrida(run)
    sitios = _ubicaciones_con_stock(run)

    fisico = _stock_por_producto(run)
    egresos = dict(
        ArcExecution.objects.filter(
            simulation_run=run, tipo_arco__in=TIPOS_ARCO_EGRESO, origen__in=sitios
        )
        .values_list("producto")
        .annotate(total=Sum("toneladas"))
    )
    cargos = {
        fila["producto"]: fila
        for fila in cargos_de_almacenaje(run, filtros)
        .values("producto")
        .annotate(
            importe_usd=Sum("importe_usd"), eventos=Count("id"), toneladas_dia=Sum("cantidad")
        )
    }

    total = sum(fila["importe_usd"] or 0.0 for fila in cargos.values())
    filas = []
    for producto in sorted({*fisico, *cargos}):
        stock_tn_dia = (fisico.get(producto) or {}).get("stock_tn_dia")
        ingresos = (fisico.get(producto) or {}).get("ingresos_tn")
        cargo = cargos.get(producto)
        importe = cargo["importe_usd"] if cargo else None
        filas.append(
            {
                "producto": producto,
                "ingresos_tn": ingresos,
                "egresos_tn": egresos.get(producto),
                "stock_promedio_tn": stock_tn_dia / dias if stock_tn_dia and dias else None,
                "stock_maximo_tn": (fisico.get(producto) or {}).get("stock_maximo_tn"),
                "dias_promedio_deposito": (
                    stock_tn_dia / ingresos if stock_tn_dia and ingresos else None
                ),
                "toneladas_dia": cargo["toneladas_dia"] if cargo else None,
                "costo_almacenaje_usd": importe,
                "eventos": cargo["eventos"] if cargo else 0,
                "usd_por_tn_ingresada": (
                    importe / ingresos if importe is not None and ingresos else None
                ),
                "porcentaje": importe / total if importe is not None and total else None,
            }
        )

    return {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "filtros_aplicados": filtros.como_dict(),
        "dias_de_la_corrida": dias,
        "costo_almacenaje_total_usd": total or None,
        "filas": sorted(filas, key=lambda fila: -(fila["costo_almacenaje_usd"] or 0.0)),
        "base_dias": BASE_DIAS,
        "base_egresos": BASE_EGRESOS,
        "base_sitios": BASE_SITIOS,
        "depositos": sitios,
        "descuadre_contra_snapshot": descuadre_contra_snapshot(run),
    }


def descuadre_contra_snapshot(run: SimulationRun) -> dict:
    """`snapshot_inventario` declara su propio costo diario y no cierra contra `costos_eventos`."""
    declarado = 0.0
    filas = 0
    consulta = InventorySnapshot.objects.filter(simulation_run=run).values_list("extra", flat=True)
    for extra in consulta:
        valor = _numero(extra.get(CAMPO_COSTO_DECLARADO))
        if valor is not None:
            declarado += valor
            filas += 1
    contable = (
        CostCharge.objects.filter(
            simulation_run=run, tipo_contable=TipoContable.CAJA, categoria=CATEGORIA_ALMACENAJE
        ).aggregate(total=Sum("importe_usd"))["total"]
        or 0.0
    )
    if not filas:
        return {"filas_declaradas": 0, "declarado_usd": None, "contable_usd": contable}
    return {
        "filas_declaradas": filas,
        "declarado_usd": declarado,
        "contable_usd": contable,
        "diferencia_usd": declarado - contable,
        "nota": (
            "los importes del tablero salen de costos_eventos; snapshot_inventario declara "
            "costo_almacenaje_dia_usd por su cuenta y no coincide"
        ),
    }


def _decision_de_deposito(run: SimulationRun, ubicacion: str) -> dict:
    """Como le fue a este deposito cada vez que el modelo lo evaluo como origen de stock."""
    alternativas = DecisionAlternative.objects.filter(simulation_run=run, origen_stock=ubicacion)
    agregado = alternativas.aggregate(
        evaluaciones=Count("id"),
        orden_ranking_promedio=Avg("orden_ranking"),
        elegida=Count("id", filter=Q(resultado_ejecucion="ELEGIDA")),
        no_factible=Count("id", filter=Q(factible=False)),
        mas_barata_no_factible=Count("id", filter=Q(es_mas_barata_no_factible=True)),
        toneladas_tomadas=Sum("toneladas_tomadas"),
    )
    motivos = [
        {"codigo_motivo": fila["codigo_motivo"] or "SIN_MOTIVO", "veces": fila["veces"]}
        for fila in alternativas.exclude(resultado_ejecucion="ELEGIDA")
        .values("codigo_motivo")
        .annotate(veces=Count("id"))
        .order_by("-veces")
    ]
    return {
        **agregado,
        "motivos_de_descarte": motivos,
        "base_ranking": (
            "orden_ranking promedio de todas las alternativas de este origen; el pseudo-origen "
            f"{PSEUDO_ORIGEN} (transferencia deposito-deposito, ranking 0) no es un sitio y "
            "no entra"
        ),
    }


def flujo_y_decision(run: SimulationRun, ubicacion: str) -> dict:
    """Flujo fisico, costo por tramo y motivo de decision de un deposito."""
    dias = _dias_de_la_corrida(run)
    inventario = InventorySnapshot.objects.filter(simulation_run=run, ubicacion=ubicacion)
    flujo = inventario.aggregate(
        ingresos_tn=Sum("ingresos_dia_tn"),
        stock_tn_dia=Sum("stock_fisico_tn"),
        stock_maximo_tn=Max("stock_fisico_tn"),
        capacidad_tn=Max("capacidad_tn"),
        ocupacion_pico_pct=Max("ocupacion_pct"),
        lotes_abiertos_pico=Max("lotes_abiertos"),
    )
    egresos = ArcExecution.objects.filter(
        simulation_run=run, tipo_arco__in=TIPOS_ARCO_EGRESO, origen=ubicacion
    ).aggregate(toneladas=Sum("toneladas"), arcos=Count("id"))
    ingresos_arcos = ArcExecution.objects.filter(
        simulation_run=run, tipo_arco__in=TIPOS_ARCO_INGRESO, destino=ubicacion
    ).aggregate(toneladas=Sum("toneladas"), arcos=Count("id"))

    cargos = CostCharge.objects.filter(
        simulation_run=run, tipo_contable=TipoContable.CAJA, sitio=ubicacion
    )
    costo = cargos.aggregate(
        costo_ingreso_usd=Sum("importe_usd", filter=Q(categoria__in=CATEGORIAS_INGRESO)),
        costo_almacenaje_usd=Sum("importe_usd", filter=Q(categoria=CATEGORIA_ALMACENAJE)),
        costo_egreso_usd=Sum("importe_usd", filter=Q(categoria__in=CATEGORIAS_EGRESO)),
        costo_total_usd=Sum("importe_usd"),
    )

    stock_tn_dia = flujo.pop("stock_tn_dia")
    ingresos = flujo["ingresos_tn"]
    return {
        "run_id": run.run_id,
        "ubicacion": ubicacion,
        "dias_de_la_corrida": dias,
        "flujo": {
            **flujo,
            "ingresos_tn_en_arcos": ingresos_arcos["toneladas"],
            "arcos_de_ingreso": ingresos_arcos["arcos"],
            "stock_promedio_tn": stock_tn_dia / dias if stock_tn_dia and dias else None,
            "egresos_tn": egresos["toneladas"],
            "arcos_de_egreso": egresos["arcos"],
            "dias_promedio_deposito": (
                stock_tn_dia / ingresos if stock_tn_dia and ingresos else None
            ),
            "base_egresos": BASE_EGRESOS,
        },
        "costo": costo,
        "decision": _decision_de_deposito(run, ubicacion),
        "productos": [
            {
                "producto": fila["producto"],
                "stock_promedio_tn": (fila["stock_tn_dia"] / dias) if dias else None,
                "stock_maximo_tn": fila["stock_maximo_tn"],
                "ingresos_tn": fila["ingresos_tn"],
            }
            for fila in inventario.values("producto")
            .annotate(
                stock_tn_dia=Sum("stock_fisico_tn"),
                stock_maximo_tn=Max("stock_fisico_tn"),
                ingresos_tn=Sum("ingresos_dia_tn"),
            )
            .order_by("producto")
        ],
    }


def serie_diaria(run: SimulationRun, ubicacion: str) -> dict:
    """Stock fisico dia a dia por producto: distingue un pico puntual de una acumulacion."""
    filas = list(
        InventorySnapshot.objects.filter(simulation_run=run, ubicacion=ubicacion)
        .values("dia", "producto", "stock_fisico_tn", "ocupacion_pct")
        .order_by("dia", "producto")
    )
    return {
        "run_id": run.run_id,
        "ubicacion": ubicacion,
        "productos": sorted({fila["producto"] for fila in filas}),
        "dias": len({fila["dia"] for fila in filas}),
        "serie_diaria": filas,
    }


ORDENES_LOTES = {
    "costo": "-costo_almacenaje_usd",
    "dias": "-dias_con_cargo",
    "toneladas": "-toneladas",
}


def top_lotes(run: SimulationRun, filtros: FiltrosCostos, orden: str = "costo") -> dict:
    """Lotes ordenados por lo que costo tenerlos guardados."""
    filas = [
        {
            "id_lote": fila["id_lote"],
            "producto": fila["producto"],
            "sitio": fila["sitio"],
            "costo_almacenaje_usd": fila["costo_almacenaje_usd"],
            "dias_con_cargo": fila["dias_con_cargo"],
            "dia_primer_cargo": fila["dia_primer_cargo"],
            "dia_ultimo_cargo": fila["dia_ultimo_cargo"],
            "toneladas": fila["toneladas_maximas"],
            "usd_por_tn": (
                fila["costo_almacenaje_usd"] / fila["toneladas_maximas"]
                if fila["costo_almacenaje_usd"] and fila["toneladas_maximas"]
                else None
            ),
        }
        for fila in cargos_de_almacenaje(run, filtros)
        .values("id_lote", "producto", "sitio")
        .annotate(
            costo_almacenaje_usd=Sum("importe_usd"),
            dias_con_cargo=Count("dia", distinct=True),
            dia_primer_cargo=Min("dia"),
            dia_ultimo_cargo=Max("dia"),
            toneladas_maximas=Max("cantidad"),
        )
    ]
    clave = ORDENES_LOTES.get(orden)
    if clave is None:
        raise OrdenInvalido(
            f"orden desconocido {orden!r}; opciones: {', '.join(sorted(ORDENES_LOTES))}"
        )
    campo = clave.lstrip("-")
    filas.sort(key=lambda fila: -(fila[campo] or 0.0))
    return {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "filtros_aplicados": filtros.como_dict(),
        "orden": orden,
        "lotes": filas,
        "base_toneladas": (
            "toneladas = mayor cantidad facturada del lote (unidad USD_TN_DIA de costos_eventos)"
        ),
    }


def recorrido_de_lote(run: SimulationRun, id_lote: str) -> dict:
    """Recorrido fisico de un lote y lo que costo tenerlo guardado."""
    arcos = list(
        ArcExecution.objects.filter(simulation_run=run, id_lote=id_lote)
        .values(
            "dia_inicio",
            "dia_fin",
            "tipo_arco",
            "origen",
            "destino",
            "toneladas",
            "producto",
            "id_contenedor",
            "codigo_pedido",
            "estado_final",
        )
        .order_by("dia_inicio")
    )
    cargos = CostCharge.objects.filter(
        simulation_run=run, tipo_contable=TipoContable.CAJA, id_lote=id_lote
    )
    almacenaje = cargos.filter(categoria=CATEGORIA_ALMACENAJE).aggregate(
        costo_usd=Sum("importe_usd"),
        dias=Count("dia", distinct=True),
        dia_primero=Min("dia"),
        dia_ultimo=Max("dia"),
        toneladas=Max("cantidad"),
        sitio=Max("sitio"),
        producto=Max("producto"),
    )
    ingreso = ArcExecution.objects.filter(
        simulation_run=run, id_lote=id_lote, tipo_arco__in=TIPOS_ARCO_INGRESO
    ).aggregate(toneladas=Sum("toneladas"), dia=Min("dia_inicio"))
    retirado = ArcExecution.objects.filter(
        simulation_run=run, id_lote=id_lote, tipo_arco__in=TIPOS_ARCO_EGRESO
    ).aggregate(toneladas=Sum("toneladas"))

    por_categoria = [
        {
            "categoria": fila["categoria"],
            "importe_usd": fila["importe_usd"],
            "eventos": fila["eventos"],
            "etapa": ALMACENAMIENTO if fila["categoria"] == CATEGORIA_ALMACENAJE else None,
        }
        for fila in cargos.values("categoria")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
        .order_by("-importe_usd")
    ]

    ingresadas = ingreso["toneladas"]
    retiradas = retirado["toneladas"]
    return {
        "run_id": run.run_id,
        "id_lote": id_lote,
        "producto": almacenaje["producto"] or (arcos[0]["producto"] if arcos else None),
        "sitio": almacenaje["sitio"],
        "dia_ingreso": ingreso["dia"],
        "toneladas_ingresadas": ingresadas,
        "toneladas_retiradas": retiradas,
        "toneladas_sin_retirar": (
            ingresadas - retiradas if ingresadas is not None and retiradas is not None else None
        ),
        "costo_almacenaje_usd": almacenaje["costo_usd"],
        "dias_con_cargo_de_almacenaje": almacenaje["dias"],
        "dia_primer_cargo": almacenaje["dia_primero"],
        "dia_ultimo_cargo": almacenaje["dia_ultimo"],
        "toneladas_facturadas": almacenaje["toneladas"],
        "costo_por_categoria": por_categoria,
        "costo_total_usd": sum(fila["importe_usd"] or 0.0 for fila in por_categoria) or None,
        "recorrido": arcos,
        "nota_recorrido": (
            "el almacenaje no es un arco: aparece como cargo diario, no como paso del recorrido"
        ),
    }
