"""Agregados del dashboard (MOD v2.0, seccion 7).

Dos reglas que no son de esta plataforma sino del modelo:

- los importes salen **solo** de `costos_eventos` y **solo** con `tipo_contable = CAJA`
  (ADR-T04); el `ECONOMICO` se informa aparte porque es costo de oportunidad, no caja;
- un campo vacio no es cero: los promedios se calculan sobre las filas que tienen dato.
"""

from __future__ import annotations

from django.db.models import Avg, Count, F, Max, Q, Sum

from apps.core.models import (
    ArcExecution,
    AssignmentResult,
    CostCharge,
    DecisionAlternative,
    InventorySnapshot,
    ResourceCapacitySnapshot,
    SimulationRun,
    TipoContable,
)

TIPOS_ARCO_ESPERA = ("ESPERA_PORTACONTENEDOR", "ESPERA_POSICION")


def _dividir(numerador, denominador):
    if not denominador:
        return None
    return numerador / denominador


def costos(run: SimulationRun) -> dict:
    caja = CostCharge.objects.filter(simulation_run=run, tipo_contable=TipoContable.CAJA)
    economico = CostCharge.objects.filter(simulation_run=run, tipo_contable=TipoContable.ECONOMICO)

    total_caja = caja.aggregate(total=Sum("importe_usd"))["total"] or 0.0
    toneladas = (
        AssignmentResult.objects.filter(simulation_run=run).aggregate(
            tn=Sum("toneladas_entregadas")
        )["tn"]
        or 0.0
    )

    por_categoria = [
        {"categoria": fila["categoria"], "importe_usd": fila["importe"] or 0.0}
        for fila in caja.values("categoria")
        .annotate(importe=Sum("importe_usd"))
        .order_by("-importe")
    ]

    return {
        "costo_total_caja_usd": total_caja,
        "costo_total_economico_usd": economico.aggregate(total=Sum("importe_usd"))["total"] or 0.0,
        "costo_usd_tn": _dividir(total_caja, toneladas),
        "toneladas_entregadas": toneladas,
        "por_categoria": por_categoria,
        "cargos_caja": caja.count(),
        "cargos_economicos": economico.count(),
    }


def servicio(run: SimulationRun) -> dict:
    asignaciones = AssignmentResult.objects.filter(simulation_run=run)
    resumen = asignaciones.aggregate(
        asignadas=Sum("toneladas_asignadas"),
        entregadas=Sum("toneladas_entregadas"),
        ciclo=Avg("dias_ciclo_real"),
        contenedores_creados=Sum("contenedores_creados"),
        contenedores_entregados=Sum("contenedores_entregados"),
        cerradas=Count("id", filter=Q(cerrada=True)),
        canceladas=Count("id", filter=Q(cancelada=True)),
    )

    kpis = getattr(run, "kpis", None)
    valores = kpis.valores if kpis else {}

    return {
        # Si la corrida trae los KPIs del modelo se usan tal cual: recalcular "on time" con una
        # formula propia produciria un numero que no reconcilia con el tablero de PLE.
        "nivel_servicio": valores.get("nivel_servicio"),
        "atraso_promedio_dias": valores.get("atraso_promedio_dias"),
        "toneladas_asignadas": resumen["asignadas"] or 0.0,
        "toneladas_entregadas": resumen["entregadas"] or 0.0,
        "cobertura_entrega": _dividir(resumen["entregadas"] or 0.0, resumen["asignadas"] or 0.0),
        "dias_ciclo_promedio": resumen["ciclo"],
        "contenedores_creados": resumen["contenedores_creados"] or 0,
        "contenedores_entregados": resumen["contenedores_entregados"] or 0,
        "asignaciones": asignaciones.count(),
        "asignaciones_cerradas": resumen["cerradas"],
        "asignaciones_canceladas": resumen["canceladas"],
    }


def restriccion(run: SimulationRun) -> dict:
    """Los KPIs nuevos del MVP: que limita la red y cuanto cuesta esa restriccion."""
    decisiones = DecisionAlternative.objects.filter(simulation_run=run)

    motivos = [
        {"codigo_motivo": fila["codigo_motivo"], "alternativas": fila["cantidad"]}
        for fila in decisiones.exclude(codigo_motivo="")
        .values("codigo_motivo")
        .annotate(cantidad=Count("id"))
        .order_by("-cantidad")
    ]

    mas_baratas = decisiones.filter(es_mas_barata_no_factible=True)
    esperas = [
        {
            "tipo_arco": fila["tipo_arco"],
            "eventos": fila["eventos"],
            "espera_promedio_horas": fila["promedio"],
            "espera_maxima_horas": fila["maximo"],
        }
        for fila in ArcExecution.objects.filter(
            simulation_run=run, tipo_arco__in=TIPOS_ARCO_ESPERA
        )
        .values("tipo_arco")
        .annotate(
            eventos=Count("id"),
            promedio=Avg("duracion_real_horas"),
            maximo=Max("duracion_real_horas"),
        )
        .order_by("tipo_arco")
    ]

    return {
        "alternativas_evaluadas": decisiones.count(),
        "alternativas_no_factibles": decisiones.filter(resultado_ejecucion="NO_FACTIBLE").count(),
        "alternativas_intentadas_fallidas": decisiones.filter(
            resultado_ejecucion="INTENTADA_FALLIDA"
        ).count(),
        "mas_baratas_no_factibles": mas_baratas.count(),
        "pedidos_con_alternativa_mas_barata_no_factible": mas_baratas.values("codigo_pedido")
        .distinct()
        .count(),
        "por_motivo": motivos,
        "esperas": esperas,
    }


def capacidad(run: SimulationRun) -> dict:
    filas = ResourceCapacitySnapshot.objects.filter(simulation_run=run)
    por_recurso = [
        {
            "tipo_recurso": fila["tipo_recurso"],
            "ubicacion": fila["ubicacion"],
            "capacidad_nominal": fila["nominal"],
            "ocupacion_promedio": fila["ocupacion_promedio"],
            "ocupacion_maxima": fila["ocupacion_maxima"],
            "cola_maxima": fila["cola_maxima"],
        }
        for fila in filas.values("tipo_recurso", "ubicacion")
        .annotate(
            nominal=Max("capacidad_nominal"),
            ocupacion_promedio=Avg("ocupada"),
            ocupacion_maxima=Max("ocupada"),
            cola_maxima=Max("cola"),
        )
        .order_by("tipo_recurso", "ubicacion")
    ]

    for fila in por_recurso:
        fila["uso_pico_pct"] = (
            None
            if not fila["capacidad_nominal"]
            else 100.0 * (fila["ocupacion_maxima"] or 0.0) / fila["capacidad_nominal"]
        )

    return {"por_recurso": por_recurso, "dias": filas.values("dia").distinct().count()}


def inventario(run: SimulationRun) -> dict:
    filas = InventorySnapshot.objects.filter(simulation_run=run)
    serie = list(
        filas.values("dia")
        .annotate(stock_fisico_tn=Sum("stock_fisico_tn"), stock_libre_tn=Sum("stock_libre_tn"))
        .order_by("dia")
    )
    return {
        "serie_diaria": serie,
        "ocupacion_pico_pct": filas.aggregate(pico=Max("ocupacion_pct"))["pico"],
        "filas_con_descuadre": filas.exclude(descuadre_tn=0)
        .exclude(descuadre_tn__isnull=True)
        .count(),
    }


def calidad(run: SimulationRun) -> dict:
    ultimo = run.imports.first()
    return {
        "estado_ultima_importacion": ultimo.estado if ultimo else None,
        "version_esquema": run.version_esquema,
        "mensajes": ultimo.mensajes if ultimo else [],
        "filas_por_tabla": ultimo.filas_por_tabla if ultimo else {},
    }


def dashboard(run: SimulationRun) -> dict:
    if not run.tiene_drill_down:
        # Corrida de barrido: solo existen los KPIs agregados (MOD v2.0, seccion 5.3, R-03).
        kpis = getattr(run, "kpis", None)
        return {
            "run_id": run.run_id,
            "tipo": run.tipo,
            "tiene_drill_down": False,
            "motivo_sin_drill_down": (
                "la corrida se ejecuto con nivelAuditoriaRed = DESACTIVADA: el barrido no escribe "
                "las tablas de auditoria, asi que no hay vista por pedido para esta corrida"
            ),
            "kpis_barrido": kpis.valores if kpis else {},
        }

    return {
        "run_id": run.run_id,
        "tipo": run.tipo,
        "tiene_drill_down": True,
        "servicio": servicio(run),
        "costos": costos(run),
        "restriccion": restriccion(run),
        "capacidad": capacidad(run),
        "inventario": inventario(run),
        "calidad": calidad(run),
    }


def por_que(run: SimulationRun, codigo_pedido: str) -> dict:
    """CU-04: la union ya resuelta decisiones -> asignaciones -> arcos -> costos."""
    decisiones = DecisionAlternative.objects.filter(
        simulation_run=run, codigo_pedido=codigo_pedido
    ).order_by("ronda", "orden_ranking")
    asignaciones = AssignmentResult.objects.filter(
        simulation_run=run, codigo_pedido=codigo_pedido
    ).order_by("dia_asignacion")
    ids_asignacion = [a.id_asignacion for a in asignaciones]

    arcos = ArcExecution.objects.filter(simulation_run=run).filter(
        Q(codigo_pedido=codigo_pedido) | Q(id_asignacion__in=ids_asignacion)
    ).order_by("dia_inicio")

    cargos = CostCharge.objects.filter(simulation_run=run).filter(
        Q(codigo_pedido=codigo_pedido) | Q(id_asignacion__in=ids_asignacion)
    ).order_by("dia")

    elegida = decisiones.filter(resultado_ejecucion="ELEGIDA").first()
    mas_barata_no_factible = (
        decisiones.filter(es_mas_barata_no_factible=True)
        .order_by("costo_incremental_usd_tn")
        .first()
    )

    costo_restriccion = None
    if elegida and mas_barata_no_factible:
        elegido = elegida.costo_incremental_usd_tn
        alternativa = mas_barata_no_factible.costo_incremental_usd_tn
        if elegido is not None and alternativa is not None:
            costo_restriccion = elegido - alternativa

    return {
        "run_id": run.run_id,
        "codigo_pedido": codigo_pedido,
        "decisiones": decisiones,
        "asignaciones": asignaciones,
        "arcos": arcos,
        "cargos": cargos,
        "resumen": {
            "alternativas_evaluadas": decisiones.count(),
            "alternativas_no_factibles": decisiones.filter(
                resultado_ejecucion="NO_FACTIBLE"
            ).count(),
            "hay_mas_barata_no_factible": mas_barata_no_factible is not None,
            "sobrecosto_de_la_restriccion_usd_tn": costo_restriccion,
            "costo_caja_usd": cargos.filter(tipo_contable=TipoContable.CAJA).aggregate(
                total=Sum("importe_usd")
            )["total"]
            or 0.0,
            "horas_de_espera": arcos.filter(tipo_arco__in=TIPOS_ARCO_ESPERA).aggregate(
                total=Sum("duracion_real_horas")
            )["total"],
            "arcos_fuera_de_lo_esperado": arcos.filter(
                duracion_esperada_horas__gte=0,
                duracion_real_horas__gt=F("duracion_esperada_horas"),
            ).count(),
        },
    }


def comparar(run_a: SimulationRun, run_b: SimulationRun) -> dict:
    """CU-05: diferencia de los KPIs agregados entre dos corridas."""
    kpis_a = getattr(run_a, "kpis", None)
    kpis_b = getattr(run_b, "kpis", None)
    valores_a = kpis_a.valores if kpis_a else {}
    valores_b = kpis_b.valores if kpis_b else {}

    filas = []
    for kpi in sorted(set(valores_a) | set(valores_b)):
        a = valores_a.get(kpi)
        b = valores_b.get(kpi)
        diferencia = None if a is None or b is None else b - a
        variacion = None if diferencia is None or not a else 100.0 * diferencia / a
        filas.append(
            {"kpi": kpi, "a": a, "b": b, "diferencia": diferencia, "variacion_pct": variacion}
        )

    return {
        "a": {"run_id": run_a.run_id, "escenario": run_a.scenario.codigo},
        "b": {"run_id": run_b.run_id, "escenario": run_b.scenario.codigo},
        "kpis": filas,
        "sin_kpis": not valores_a or not valores_b,
    }
