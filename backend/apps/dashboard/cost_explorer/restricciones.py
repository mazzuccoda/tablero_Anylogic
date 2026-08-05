"""Sobrecosto por restriccion (MOD v3.2, seccion D).

La pregunta es "que restriccion me hizo pagar mas de lo necesario". El contrapunto lo escribe
AnyLogic: cuando descarta la alternativa mas barata por una restriccion, marca esa fila con
`es_mas_barata_no_factible` y deja en el CSV el costo unitario que **habria** tenido
(`costo_unitario_sin_restriccion`, o `costo_incremental_usd_tn` si el modelo lo publica ahi) junto
al de la que finalmente eligio (`costo_elegida_usd_tn`).

Ese par vive en `extra` porque el MVP no promovio esas dos columnas a campos del modelo, asi que el
calculo se hace en Python sobre dos consultas chicas (en el paquete real, 1.413 elegidas y 472
alternativas marcadas), no fila por fila sobre los 106.365 cargos.

Dos cosas que no se hacen aca:

- no se toca `costos_eventos`: el sobrecosto es un **contrafactual**, no un cargo. Se publica en su
  propio endpoint y no entra en ninguna reconciliacion de importes;
- no se supone que la alternativa bloqueada podia mover todas las toneladas: se informan las
  toneladas efectivamente tomadas por la elegida y, al lado, las que la bloqueada declaraba
  factibles, para que se vea cuando el contrafactual es parcial.
"""

from __future__ import annotations

from apps.core.models import DecisionAlternative, SimulationRun

CAMPO_COSTO_SIN_RESTRICCION = "costo_unitario_sin_restriccion"
CAMPO_COSTO_ELEGIDA = "costo_elegida_usd_tn"
SIN_MOTIVO = "SIN_MOTIVO"


def _numero(valor: object) -> float | None:
    """`extra` guarda los numeros como texto tal cual vinieron del CSV."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def costo_unitario_elegida(alternativa: DecisionAlternative) -> float | None:
    """Costo unitario de la alternativa que se ejecuto.

    El paquete real deja `costo_incremental_usd_tn` vacio en muchas filas y publica el mismo numero
    en `costo_elegida_usd_tn`. Vive aca y no en cada vista para que el Cost Explorer y el "por que"
    del pedido no contesten distinto sobre la misma decision.
    """
    if alternativa.costo_incremental_usd_tn is not None:
        return alternativa.costo_incremental_usd_tn
    return _numero(alternativa.extra.get(CAMPO_COSTO_ELEGIDA))


def costo_unitario_sin_restriccion(alternativa: DecisionAlternative) -> float | None:
    """Costo unitario que habria tenido una alternativa descartada por una restriccion."""
    costo = _numero(alternativa.extra.get(CAMPO_COSTO_SIN_RESTRICCION))
    if costo is None:
        return alternativa.costo_incremental_usd_tn
    return costo


def _elegidas(run: SimulationRun) -> dict[str, dict]:
    """Costo unitario y toneladas tomadas por decision, ponderando si hubo asignacion parcial."""
    elegidas: dict[str, dict] = {}
    consulta = DecisionAlternative.objects.filter(
        simulation_run=run, resultado_ejecucion="ELEGIDA"
    ).only(
        "id_decision",
        "codigo_pedido",
        "producto",
        "circuito",
        "origen_stock",
        "costo_incremental_usd_tn",
        "toneladas_tomadas",
        "extra",
    )
    for alternativa in consulta:
        datos = elegidas.setdefault(
            alternativa.id_decision,
            {
                "codigo_pedido": alternativa.codigo_pedido,
                "producto": alternativa.producto,
                "circuito": alternativa.circuito,
                "origen_stock": alternativa.origen_stock,
                "toneladas": 0.0,
                "costo_por_tn": 0.0,
            },
        )
        toneladas = alternativa.toneladas_tomadas or 0.0
        costo = costo_unitario_elegida(alternativa)
        if costo is not None:
            datos["costo_por_tn"] += costo * toneladas
        datos["toneladas"] += toneladas

    for datos in elegidas.values():
        datos["costo_usd_tn"] = (
            datos.pop("costo_por_tn") / datos["toneladas"] if datos["toneladas"] else None
        )
    return elegidas


def _bloqueadas(run: SimulationRun) -> dict[str, dict]:
    """La alternativa mas barata descartada de cada decision: dice cuanto costaba evitarla."""
    bloqueadas: dict[str, dict] = {}
    consulta = DecisionAlternative.objects.filter(
        simulation_run=run, es_mas_barata_no_factible=True
    ).only(
        "id_decision",
        "codigo_motivo",
        "detalle_motivo",
        "origen_stock",
        "costo_incremental_usd_tn",
        "toneladas_factibles",
        "toneladas_solicitadas",
        "extra",
    )
    for alternativa in consulta:
        costo = costo_unitario_sin_restriccion(alternativa)
        if costo is None:
            continue
        actual = bloqueadas.get(alternativa.id_decision)
        if actual is not None and actual["costo_usd_tn"] <= costo:
            continue
        bloqueadas[alternativa.id_decision] = {
            "codigo_motivo": alternativa.codigo_motivo or SIN_MOTIVO,
            "detalle_motivo": alternativa.detalle_motivo,
            "origen_bloqueado": alternativa.origen_stock,
            "costo_usd_tn": costo,
            "toneladas_declaradas": alternativa.toneladas_factibles
            or alternativa.toneladas_solicitadas,
        }
    return bloqueadas


def sobrecosto_por_decision(run: SimulationRun) -> list[dict]:
    """Una fila por decision donde la restriccion encarecio la solucion."""
    elegidas = _elegidas(run)
    filas = []
    for id_decision, bloqueada in _bloqueadas(run).items():
        elegida = elegidas.get(id_decision)
        if elegida is None or elegida["costo_usd_tn"] is None:
            continue
        sobrecosto_usd_tn = elegida["costo_usd_tn"] - bloqueada["costo_usd_tn"]
        if sobrecosto_usd_tn <= 0:
            continue
        toneladas = elegida["toneladas"]
        filas.append(
            {
                "id_decision": id_decision,
                "codigo_pedido": elegida["codigo_pedido"],
                "producto": elegida["producto"],
                "circuito": elegida["circuito"],
                "origen_elegido": elegida["origen_stock"],
                "origen_bloqueado": bloqueada["origen_bloqueado"],
                "codigo_motivo": bloqueada["codigo_motivo"],
                "detalle_motivo": bloqueada["detalle_motivo"],
                "costo_elegida_usd_tn": elegida["costo_usd_tn"],
                "costo_sin_restriccion_usd_tn": bloqueada["costo_usd_tn"],
                "sobrecosto_usd_tn": sobrecosto_usd_tn,
                "toneladas": toneladas,
                "toneladas_declaradas_por_la_bloqueada": bloqueada["toneladas_declaradas"],
                "sobrecosto_usd": sobrecosto_usd_tn * toneladas,
            }
        )
    return sorted(filas, key=lambda fila: -fila["sobrecosto_usd"])


def sobrecosto_por_restriccion(run: SimulationRun) -> dict:
    """Agrega el sobrecosto por `codigo_motivo`: el ranking de restricciones que salen mas caras."""
    filas = sobrecosto_por_decision(run)
    por_motivo: dict[str, dict] = {}
    for fila in filas:
        motivo = por_motivo.setdefault(
            fila["codigo_motivo"],
            {
                "codigo_motivo": fila["codigo_motivo"],
                "sobrecosto_usd": 0.0,
                "toneladas": 0.0,
                "decisiones": 0,
                "pedidos": set(),
            },
        )
        motivo["sobrecosto_usd"] += fila["sobrecosto_usd"]
        motivo["toneladas"] += fila["toneladas"]
        motivo["decisiones"] += 1
        if fila["codigo_pedido"]:
            motivo["pedidos"].add(fila["codigo_pedido"])

    ranking = []
    for motivo in por_motivo.values():
        pedidos = motivo.pop("pedidos")
        motivo["pedidos"] = len(pedidos)
        motivo["sobrecosto_usd_tn"] = (
            motivo["sobrecosto_usd"] / motivo["toneladas"] if motivo["toneladas"] else None
        )
        ranking.append(motivo)
    ranking.sort(key=lambda fila: -fila["sobrecosto_usd"])

    return {
        "run_id": run.run_id,
        "sobrecosto_total_usd": sum(fila["sobrecosto_usd"] for fila in filas),
        "decisiones_afectadas": len(filas),
        "por_restriccion": ranking,
        "decisiones": filas,
        "definicion": (
            "sobrecosto = (costo unitario de la alternativa elegida - costo unitario de la "
            "alternativa mas barata que la restriccion bloqueo) x toneladas tomadas. Es un "
            "contrafactual del modelo, no un cargo de costos_eventos, y no entra en ningun total."
        ),
    }
