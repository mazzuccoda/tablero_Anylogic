"""Ruta fisica de una asignacion (ADR-T06, MOD v6).

Ningun archivo del paquete declara una "ruta" con nombre: `circuito` es un tipo de consolidacion
(5 valores fijos — `CONSOLIDACION_DEPOSITO/PLANTA/TERMINAL`, `CROSS_DOCK_DEPOSITO`,
`SIN_DEFINIR`), no un identificador de trayecto. La ruta que importa para leer "que circuito se
uso y a que costo" es la secuencia de sitios de `ejecucion_arcos` para una `id_asignacion`,
ordenada en el tiempo real (`dia_inicio`) — por ejemplo `RUTA9→T4` o `DODERO→RUTA9→T4`.

El origen real (planta) se antepone siempre que la topologia lo determine sin ambiguedad: en el
paquete real, cada deposito (`destino` de un arco de ingreso de lote — `PLANTA_DEPOSITO` o
`CROSS_DOCK`, ver `ARCOS_INGRESO_LOTE` en `objetos.py`) se alimenta siempre desde el mismo origen —
de hecho, un unico "PLANTA" en toda la red. Esto es una propiedad del sitio, no de la
transferencia puntual de un lote: no hace falta encadenar por `id_lote` para saberlo (ver
`_origen_por_destino`).

`TERMINAL_ORIGEN_CONTENEDOR_VACIO` (494 arcos del paquete real) tampoco es un tramo del producto:
es el contenedor vacio viajando hacia el deposito para cargarse, antes de que el producto se mueva
— por eso se excluye igual que las esperas al reconstruir la cadena de sitios. Sin excluirlo, una
asignacion cuyo contenedor sale vacio desde una terminal (`T4→RUTA9`, por ejemplo) arranca su ruta
ahi en vez de en el deposito donde el producto realmente se cargo.

Tres categorias (`ALMACENAMIENTO`, `FLETE_PRODUCTO`, `IN_DEPOSITO`) no llevan `id_asignacion`
porque son cargos periodicos sobre un lote parado o moviendose entre sitios, no sobre un envio
puntual — pero SI traen `sitio` poblado (100% del paquete real). Para esas, el costo se reparte
entre las rutas fisicas que efectivamente pasan por ese sitio, ponderado por su tonelaje real
(`asignaciones_elegidas`, la misma base que ya se usa para "% estrategia") — no toda la red, solo
las rutas candidatas de ese sitio puntual. Si un lote no ambiguo ya resuelve una ruta unica
(`_ruta_unica_por_lote`), esa atribucion exacta tiene prioridad sobre el reparto por sitio.

Las asignaciones por corrida son miles, no cientos de miles: reconstruir la ruta en Python (un
`dict` de `id_asignacion -> "SITIO1→SITIO2"`) es una excepcion deliberada a la regla de
`agregados.py` de agregar todo en la base — acá no hay forma portable (SQLite y Postgres) de
concatenar una secuencia ordenada de sitios en SQL sin salir del ORM.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Sum

from apps.core.models import ArcExecution, AssignmentResult, SimulationRun

from .agregados import _porcentaje, cargos_filtrados, total_filtrado
from .clasificacion import clasificar_etapa, ordenar_por_etapa
from .filtros import FiltrosCostos
from .objetos import ARCOS_INGRESO_LOTE

# Arcos que no representan el movimiento del producto: las esperas (el producto no se movio, solo
# hizo tiempo) y el contenedor vacio yendo a cargarse (el producto todavia no viajo en el).
TIPOS_ARCO_SIN_PRODUCTO = (
    "ESPERA_PORTACONTENEDOR",
    "ESPERA_POSICION",
    "TERMINAL_ORIGEN_CONTENEDOR_VACIO",
)

SIN_RUTA = "SIN_RUTA"

# Categorias sin id_asignacion propio pero con `sitio` confiable: el costo se reparte por sitio +
# tonelaje real en vez de caer directo en SIN_RUTA (ver docstring del modulo).
CATEGORIAS_POR_SITIO = ("ALMACENAMIENTO", "FLETE_PRODUCTO", "IN_DEPOSITO")


def _origen_por_destino(run: SimulationRun) -> dict[str, str]:
    """`destino -> origen` de los tramos de ingreso de lote (`ARCOS_INGRESO_LOTE`:
    `PLANTA_DEPOSITO` y `CROSS_DOCK`), solo para los destinos que siempre se alimentan desde el
    mismo origen. No depende de `id_lote`: es una propiedad fija de cada sitio, no de una
    transferencia puntual — por eso alcanza para anteponer el origen real a cualquier ruta,
    ambigua o no aguas abajo."""
    arcos = (
        ArcExecution.objects.filter(simulation_run=run, tipo_arco__in=ARCOS_INGRESO_LOTE)
        .values("origen", "destino")
        .distinct()
    )
    origenes: dict[str, set[str]] = {}
    for a in arcos:
        origenes.setdefault(a["destino"], set()).add(a["origen"])
    return {
        destino: origenes_.pop() for destino, origenes_ in origenes.items() if len(origenes_) == 1
    }


def _rutas_por_asignacion(run: SimulationRun) -> tuple[dict[str, str], dict[str, str]]:
    """`id_asignacion -> "SITIO1→SITIO2→..."` (con el origen real antepuesto cuando la topologia
    lo permite) y, aparte, `id_asignacion -> id_lote` — lo segundo lo necesita
    `_ruta_unica_por_lote` para saber que asignaciones comparten lote."""
    tramos = (
        ArcExecution.objects.filter(simulation_run=run)
        .exclude(tipo_arco__in=TIPOS_ARCO_SIN_PRODUCTO)
        .exclude(tipo_arco__in=ARCOS_INGRESO_LOTE)
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

    origen_por_destino = _origen_por_destino(run)

    rutas: dict[str, str] = {}
    for id_asignacion, sitios in sitios_por_asignacion.items():
        if sitios:
            origen = origen_por_destino.get(sitios[0])
            if origen and origen != sitios[0]:
                sitios = [origen, *sitios]
        rutas[id_asignacion] = "→".join(sitios) if sitios else SIN_RUTA
    return rutas, lote_por_asignacion


def _ruta_unica_por_lote(
    rutas: dict[str, str], lote_por_asignacion: dict[str, str]
) -> dict[str, str]:
    """`id_lote -> ruta`, solo para los lotes cuyas asignaciones aguas abajo terminan TODAS en la
    misma ruta reconstruida. La mayoria de los lotes se reparten en varias asignaciones (el mismo
    lote alimenta varios envios) y a veces esas asignaciones van a rutas distintas — ahi la
    atribucion exacta no alcanza y el cargo pasa al reparto por sitio (o a `SIN_RUTA` si tampoco
    ese resuelve)."""
    rutas_por_lote: dict[str, set[str]] = {}
    for id_asignacion, lote in lote_por_asignacion.items():
        ruta = rutas.get(id_asignacion)
        if ruta:
            rutas_por_lote.setdefault(lote, set()).add(ruta)
    return {lote: rutas_.pop() for lote, rutas_ in rutas_por_lote.items() if len(rutas_) == 1}


def _rutas_por_sitio(rutas: dict[str, str]) -> dict[str, set[str]]:
    """`sitio -> rutas` que lo atraviesan. El candidato para repartir un cargo por sitio son las
    rutas fisicas que de verdad pasan por ahi (incluido el origen antepuesto), no toda la red."""
    resultado: dict[str, set[str]] = defaultdict(set)
    for ruta in set(rutas.values()):
        for sitio in ruta.split("→"):
            resultado[sitio].add(ruta)
    return resultado


def _toneladas_por_ruta(
    run: SimulationRun, filtros: FiltrosCostos, rutas: dict[str, str]
) -> dict[str, float]:
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
    return toneladas_por_ruta


def _repartir_por_sitio(
    sitio: str,
    rutas_por_sitio: dict[str, set[str]],
    toneladas_por_ruta: dict[str, float],
) -> dict[str, float]:
    """Fraccion de un cargo por sitio que le toca a cada ruta candidata, ponderada por su
    tonelaje real. Vacio si el sitio no esta en ninguna ruta reconstruida o ninguna candidata
    tiene tonelaje: ahi no hay base para repartir y el cargo se queda en `SIN_RUTA`, igual que
    cualquier "sin dato" del tablero."""
    if not sitio:
        return {}
    candidatas = rutas_por_sitio.get(sitio, set())
    pesos = {ruta: toneladas_por_ruta.get(ruta, 0.0) for ruta in candidatas}
    total_peso = sum(pesos.values())
    if total_peso <= 0:
        return {}
    return {ruta: tn / total_peso for ruta, tn in pesos.items() if tn > 0}


def _resolver_grupo(
    fila: dict,
    rutas: dict[str, str],
    ruta_por_lote: dict[str, str],
    rutas_por_sitio: dict[str, set[str]],
    toneladas_por_ruta: dict[str, float],
) -> dict[str, float]:
    """Como se reparte el importe de un grupo (id_asignacion, id_lote, categoria, sitio) entre
    rutas: `{ruta: fraccion}` que suma 1.0. Prioridad: id_asignacion exacto, despues id_lote no
    ambiguo, despues reparto por sitio+tonelaje (solo para `CATEGORIAS_POR_SITIO`), y si nada de
    eso resuelve, todo el importe a `SIN_RUTA`."""
    id_asignacion = fila["id_asignacion"]
    id_lote = fila["id_lote"]
    if id_asignacion and id_asignacion in rutas:
        return {rutas[id_asignacion]: 1.0}
    if id_lote and id_lote in ruta_por_lote:
        return {ruta_por_lote[id_lote]: 1.0}
    if fila["categoria"] in CATEGORIAS_POR_SITIO:
        reparto = _repartir_por_sitio(fila["sitio"], rutas_por_sitio, toneladas_por_ruta)
        if reparto:
            return reparto
    return {SIN_RUTA: 1.0}


def costos_por_ruta(run: SimulationRun, filtros: FiltrosCostos) -> list[dict]:
    """Costo y toneladas por ruta fisica reconstruida. Un cargo sin `id_asignacion` se resuelve
    por `id_lote` cuando ese lote solo alimento una ruta, o se reparte por sitio + tonelaje real
    cuando la categoria lo permite (ver docstring del modulo); lo que ninguna de las dos formas
    resuelve cae en `SIN_RUTA`, no se descarta — igual que cualquier "sin dato" del tablero.
    """
    total = total_filtrado(run, filtros)
    rutas, lote_por_asignacion = _rutas_por_asignacion(run)
    ruta_por_lote = _ruta_unica_por_lote(rutas, lote_por_asignacion)
    rutas_por_sitio = _rutas_por_sitio(rutas)
    toneladas_por_ruta = _toneladas_por_ruta(run, filtros, rutas)

    por_grupo = (
        cargos_filtrados(run, filtros)
        .values("id_asignacion", "id_lote", "categoria", "sitio")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
    )
    costo_por_ruta: dict[str, dict] = {}
    for fila in por_grupo:
        reparto = _resolver_grupo(fila, rutas, ruta_por_lote, rutas_por_sitio, toneladas_por_ruta)
        importe = fila["importe_usd"] or 0.0
        for ruta, fraccion in reparto.items():
            acumulado = costo_por_ruta.setdefault(ruta, {"importe_usd": 0.0, "eventos": 0})
            acumulado["importe_usd"] += importe * fraccion
            acumulado["eventos"] += fila["eventos"] * fraccion

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
    reconstruccion y reparto de ruta que `costos_por_ruta`, pero conservando la etapa de cada
    cargo en vez de colapsarla en un total. Sin toneladas: esas solo tienen sentido a nivel ruta
    (vienen de la asignacion completa), no repartidas por etapa.
    """
    rutas, lote_por_asignacion = _rutas_por_asignacion(run)
    ruta_por_lote = _ruta_unica_por_lote(rutas, lote_por_asignacion)
    rutas_por_sitio = _rutas_por_sitio(rutas)
    toneladas_por_ruta = _toneladas_por_ruta(run, filtros, rutas)

    por_celda = (
        cargos_filtrados(run, filtros)
        .values("id_asignacion", "id_lote", "categoria", "sitio")
        .annotate(importe_usd=Sum("importe_usd"), eventos=Count("id"))
    )
    celdas: dict[tuple[str, str], dict] = {}
    for fila in por_celda:
        reparto = _resolver_grupo(fila, rutas, ruta_por_lote, rutas_por_sitio, toneladas_por_ruta)
        etapa = clasificar_etapa(fila["categoria"])
        importe = fila["importe_usd"] or 0.0
        for ruta, fraccion in reparto.items():
            clave = (ruta, etapa)
            acumulado = celdas.setdefault(
                clave, {"ruta": ruta, "etapa": etapa, "importe_usd": 0.0, "eventos": 0}
            )
            acumulado["importe_usd"] += importe * fraccion
            acumulado["eventos"] += fila["eventos"] * fraccion
    return ordenar_por_etapa(list(celdas.values()))
