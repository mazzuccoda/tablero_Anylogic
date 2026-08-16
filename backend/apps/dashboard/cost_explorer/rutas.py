"""Ruta fisica de una asignacion (ADR-T06, MOD v6).

Ningun archivo del paquete declara una "ruta" con nombre: `circuito` es un tipo de consolidacion
(5 valores fijos — `CONSOLIDACION_DEPOSITO/PLANTA/TERMINAL`, `CROSS_DOCK_DEPOSITO`,
`SIN_DEFINIR`), no un identificador de trayecto. La ruta que importa para leer "que circuito se
uso y a que costo" es la secuencia de sitios de `ejecucion_arcos` para una `id_asignacion`,
ordenada en el tiempo real (`dia_inicio`) — por ejemplo `RUTA9→T4` o `DODERO→RUTA9→T4`.

El tramo planta->deposito es un caso aparte: sus arcos (`tipo_arco = PLANTA_DEPOSITO`) llevan un
`id_asignacion` propio con prefijo `TRA-` — un identificador de *transferencia*, distinto del
`id_asignacion` (prefijo `ASG-`) del envio final al cliente que arma el resto de la ruta. Sin
tratarlo aparte, la ruta reconstruida arranca en el deposito y pierde el primer tramo real (el
que corresponde a la etapa TRANSFERENCIA_PLANTA_DEPOSITO). El punto de union entre las dos
transferencias es `id_lote`, que si esta poblado en ambas.

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
PLANTA_DEPOSITO = "PLANTA_DEPOSITO"

SIN_RUTA = "SIN_RUTA"


def _tramos_planta_por_lote(run: SimulationRun) -> dict[str, dict[str, tuple[str, str]]]:
    """`id_lote -> {destino: (origen, destino)}` de cada tramo planta->deposito de ese lote.

    Un mismo lote puede haberse transferido a mas de un deposito en transferencias distintas
    (81 de los lotes del paquete real, por ejemplo) — por eso el diccionario interno esta
    indexado por destino: al buscar por el primer sitio de la ruta descendente, el match es
    exacto o no hay match, nunca ambiguo.
    """
    arcos = (
        ArcExecution.objects.filter(simulation_run=run, tipo_arco=PLANTA_DEPOSITO)
        .exclude(id_lote="")
        .values("id_lote", "origen", "destino")
        .distinct()
    )
    resultado: dict[str, dict[str, tuple[str, str]]] = {}
    for a in arcos:
        resultado.setdefault(a["id_lote"], {})[a["destino"]] = (a["origen"], a["destino"])
    return resultado


def _rutas_por_asignacion(run: SimulationRun) -> tuple[dict[str, str], dict[str, str]]:
    """`id_asignacion -> "SITIO1→SITIO2→..."` (con el tramo planta->deposito antepuesto cuando se
    puede resolver sin ambiguedad) y, aparte, `id_asignacion -> id_lote` — lo segundo lo necesita
    `_ruta_unica_por_lote` para saber que asignaciones comparten lote."""
    tramos = (
        ArcExecution.objects.filter(simulation_run=run)
        .exclude(tipo_arco__in=TIPOS_ARCO_ESPERA)
        .exclude(tipo_arco=PLANTA_DEPOSITO)
        .exclude(id_asignacion="")
        .order_by("id_asignacion", "dia_inicio")
        .values("id_asignacion", "id_lote", "origen", "destino")
    )
    sitios_por_asignacion: dict[str, list[str]] = {}
    lote_por_asignacion: dict[str, str] = {}
    for tramo in tramos:
        sitios = sitios_por_asignacion.setdefault(tramo["id_asignacion"], [])
        if not sitios and tramo["origen"]:
            sitios.append(tramo["origen"])
        if tramo["destino"] and (not sitios or sitios[-1] != tramo["destino"]):
            sitios.append(tramo["destino"])
        if tramo["id_lote"] and tramo["id_asignacion"] not in lote_por_asignacion:
            lote_por_asignacion[tramo["id_asignacion"]] = tramo["id_lote"]

    tramos_planta = _tramos_planta_por_lote(run)

    rutas: dict[str, str] = {}
    for id_asignacion, sitios in sitios_por_asignacion.items():
        if sitios:
            lote = lote_por_asignacion.get(id_asignacion)
            tramo_planta = tramos_planta.get(lote, {}).get(sitios[0]) if lote else None
            if tramo_planta and tramo_planta[0] != sitios[0]:
                sitios = [tramo_planta[0], *sitios]
        rutas[id_asignacion] = "→".join(sitios) if sitios else SIN_RUTA
    return rutas, lote_por_asignacion


def _ruta_unica_por_lote(
    rutas: dict[str, str], lote_por_asignacion: dict[str, str]
) -> dict[str, str]:
    """`id_lote -> ruta`, solo para los lotes cuyas asignaciones aguas abajo terminan TODAS en la
    misma ruta reconstruida. La mayoria de los lotes se reparten en varias asignaciones (el mismo
    lote alimenta varios envios) y a veces esas asignaciones van a rutas distintas — ahi no hay
    forma de saber, sin inventar un prorrateo, cuanto del costo del lote (ALMACENAMIENTO,
    FLETE_PRODUCTO, IN_DEPOSITO: cargos que no llevan `id_asignacion` propio) le corresponde a
    cada ruta. Solo se resuelve el caso sin ambiguedad: una ruta, o ninguna."""
    rutas_por_lote: dict[str, set[str]] = {}
    for id_asignacion, lote in lote_por_asignacion.items():
        ruta = rutas.get(id_asignacion)
        if ruta:
            rutas_por_lote.setdefault(lote, set()).add(ruta)
    return {lote: rutas_.pop() for lote, rutas_ in rutas_por_lote.items() if len(rutas_) == 1}


def _ruta_de(
    id_asignacion: str,
    id_lote: str,
    rutas: dict[str, str],
    ruta_por_lote: dict[str, str],
) -> str:
    if id_asignacion and id_asignacion in rutas:
        return rutas[id_asignacion]
    if id_lote and id_lote in ruta_por_lote:
        return ruta_por_lote[id_lote]
    return SIN_RUTA


def costos_por_ruta(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Costo (via `costos_eventos`, agrupado en la base) y toneladas (via `asignaciones_elegidas`)
    por ruta fisica reconstruida. Un cargo sin `id_asignacion` se resuelve por `id_lote` cuando
    ese lote solo alimento una ruta (ver `_ruta_unica_por_lote`); si no se puede resolver de
    ninguna forma cae en `SIN_RUTA`, no se descarta — igual que cualquier "sin dato" del tablero.
    """
    total = total_filtrado(run, filtros)
    rutas, lote_por_asignacion = _rutas_por_asignacion(run)
    ruta_por_lote = _ruta_unica_por_lote(rutas, lote_por_asignacion)

    por_asignacion = (
        cargos_filtrados(run, filtros)
        .values("id_asignacion", "id_lote")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
    )
    costo_por_ruta: dict[str, dict] = {}
    for fila in por_asignacion:
        ruta = _ruta_de(fila["id_asignacion"], fila["id_lote"], rutas, ruta_por_lote)
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
    reconstruccion de ruta que `costos_por_ruta` (incluida la resolucion por lote), pero
    conservando la etapa de cada cargo en vez de colapsarla en un total. Sin toneladas: esas solo
    tienen sentido a nivel ruta (vienen de la asignacion completa), no repartidas por etapa.
    """
    rutas, lote_por_asignacion = _rutas_por_asignacion(run)
    ruta_por_lote = _ruta_unica_por_lote(rutas, lote_por_asignacion)

    por_celda = (
        cargos_filtrados(run, filtros)
        .values("id_asignacion", "id_lote", "categoria")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
    )
    celdas: dict[tuple[str, str], dict] = {}
    for fila in por_celda:
        ruta = _ruta_de(fila["id_asignacion"], fila["id_lote"], rutas, ruta_por_lote)
        etapa = clasificar_etapa(fila["categoria"])
        clave = (ruta, etapa)
        acumulado = celdas.setdefault(
            clave, {"ruta": ruta, "etapa": etapa, "importe_usd": 0.0, "eventos": 0}
        )
        acumulado["importe_usd"] += fila["importe_usd"] or 0.0
        acumulado["eventos"] += fila["eventos"]
    return ordenar_por_etapa(list(celdas.values()))
