"""Ruta fisica de una asignacion (ADR-T06, MOD v6).

Ningun archivo del paquete declara una "ruta" con nombre: `circuito` es un tipo de consolidacion
(5 valores fijos — `CONSOLIDACION_DEPOSITO/PLANTA/TERMINAL`, `CROSS_DOCK_DEPOSITO`,
`SIN_DEFINIR`), no un identificador de trayecto. La ruta que importa para leer "que circuito se
uso y a que costo" es la secuencia de sitios de `ejecucion_arcos` para una `id_asignacion`,
ordenada en el tiempo real (`dia_inicio`) — por ejemplo `RUTA9→T4` o `DODERO→RUTA9→T4`.

Las asignaciones por corrida son miles, no cientos de miles: reconstruir la ruta en Python (un
`dict` de `id_asignacion -> "SITIO1→SITIO2"`) es una excepcion deliberada a la regla de
`agregados.py` de agregar todo en la base — acá no hay forma portable (SQLite y Postgres) de
concatenar una secuencia ordenada de sitios en SQL sin salir del ORM.
"""

from __future__ import annotations

from django.db.models import Count, Sum

from apps.core.models import ArcExecution, AssignmentResult, SimulationRun

from .agregados import _porcentaje, cargos_filtrados, total_filtrado
from .clasificacion import clasificar_etapa, ordenar_por_etapa
from .filtros import FiltrosCostos

# Las esperas no representan un sitio nuevo: el producto no se movio, solo hizo tiempo.
TIPOS_ARCO_ESPERA = ("ESPERA_PORTACONTENEDOR", "ESPERA_POSICION")

SIN_RUTA = "SIN_RUTA"


def _rutas_por_asignacion(run: SimulationRun) -> dict[str, str]:
    """`id_asignacion -> "SITIO1→SITIO2→..."`, una consulta por corrida (no por fila)."""
    tramos = (
        ArcExecution.objects.filter(simulation_run=run)
        .exclude(tipo_arco__in=TIPOS_ARCO_ESPERA)
        .exclude(id_asignacion="")
        .order_by("id_asignacion", "dia_inicio")
        .values("id_asignacion", "origen", "destino")
    )
    sitios_por_asignacion: dict[str, list[str]] = {}
    for tramo in tramos:
        sitios = sitios_por_asignacion.setdefault(tramo["id_asignacion"], [])
        if not sitios and tramo["origen"]:
            sitios.append(tramo["origen"])
        if tramo["destino"] and (not sitios or sitios[-1] != tramo["destino"]):
            sitios.append(tramo["destino"])
    return {
        id_asignacion: "→".join(sitios) if sitios else SIN_RUTA
        for id_asignacion, sitios in sitios_por_asignacion.items()
    }


def costos_por_ruta(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Costo (via `costos_eventos`, agrupado en la base por `id_asignacion`) y toneladas (via
    `asignaciones_elegidas`) por ruta fisica reconstruida. Una asignacion sin arcos ejecutados
    (o con `id_asignacion` vacio) cae en `SIN_RUTA`, no se descarta — igual que cualquier "sin
    dato" del tablero."""
    total = total_filtrado(run, filtros)
    rutas = _rutas_por_asignacion(run)

    # No se excluye `id_asignacion=""`: categorias enteras (ALMACENAMIENTO, FLETE_PRODUCTO) no
    # llevan asignacion porque son cargos periodicos sobre inventario, no ligados a un envio.
    # Excluirlas en vez de agruparlas en SIN_RUTA violaria "sin dato != se descarta" y la
    # reconciliacion contra el total de la corrida dejaria de cerrar.
    por_asignacion = (
        cargos_filtrados(run, filtros)
        .values("id_asignacion")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
    )
    costo_por_ruta: dict[str, dict] = {}
    for fila in por_asignacion:
        ruta = rutas.get(fila["id_asignacion"], SIN_RUTA) if fila["id_asignacion"] else SIN_RUTA
        acumulado = costo_por_ruta.setdefault(ruta, {"importe_usd": 0.0, "eventos": 0})
        acumulado["importe_usd"] += fila["importe_usd"] or 0.0
        acumulado["eventos"] += fila["eventos"]

    asignaciones = AssignmentResult.objects.filter(simulation_run=run)
    for campo in ("producto", "material"):
        valor = filtros.exactos.get(campo)
        if valor:
            asignaciones = asignaciones.filter(**{campo: valor})

    toneladas_por_ruta: dict[str, float] = {}
    for fila in asignaciones.values("id_asignacion", "toneladas_asignadas"):
        ruta = rutas.get(fila["id_asignacion"], SIN_RUTA)
        toneladas_por_ruta[ruta] = toneladas_por_ruta.get(ruta, 0.0) + (
            fila["toneladas_asignadas"] or 0.0
        )
    toneladas_totales = sum(toneladas_por_ruta.values()) or None

    filas = []
    for ruta in set(costo_por_ruta) | set(toneladas_por_ruta):
        costo = costo_por_ruta.get(ruta)
        toneladas = toneladas_por_ruta.get(ruta)
        filas.append(
            {
                "ruta": ruta,
                "importe_usd": costo["importe_usd"] if costo else None,
                "eventos": costo["eventos"] if costo else 0,
                "porcentaje": _porcentaje(costo["importe_usd"], total) if costo else None,
                "toneladas": toneladas,
                "porcentaje_toneladas": _porcentaje(toneladas, toneladas_totales),
            }
        )
    filas.sort(key=lambda f: -(f["toneladas"] or 0))
    return filas


def costos_por_ruta_y_etapa(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Cruce etapa x ruta para la matriz "estrategia por producto" (MOD v6): misma
    reconstruccion de ruta que `costos_por_ruta`, pero conservando la etapa de cada cargo en vez
    de colapsarla en un total — es lo que arma las filas de la matriz. Sin toneladas: esas solo
    tienen sentido a nivel ruta (vienen de la asignacion completa), no repartidas por etapa.
    """
    rutas = _rutas_por_asignacion(run)
    por_celda = (
        cargos_filtrados(run, filtros)
        .values("id_asignacion", "categoria")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
    )
    celdas: dict[tuple[str, str], dict] = {}
    for fila in por_celda:
        ruta = rutas.get(fila["id_asignacion"], SIN_RUTA) if fila["id_asignacion"] else SIN_RUTA
        etapa = clasificar_etapa(fila["categoria"])
        clave = (ruta, etapa)
        acumulado = celdas.setdefault(
            clave, {"ruta": ruta, "etapa": etapa, "importe_usd": 0.0, "eventos": 0}
        )
        acumulado["importe_usd"] += fila["importe_usd"] or 0.0
        acumulado["eventos"] += fila["eventos"]
    return ordenar_por_etapa(list(celdas.values()))
