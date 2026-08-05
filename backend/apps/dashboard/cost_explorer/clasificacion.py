"""Clasificacion de etapa logistica y de geografia.

`categoria` viene poblada en el 100 % del importe del paquete real de AnyLogic y tiene diez valores
para `CAJA` mas uno para `ECONOMICO`, asi que la etapa sale de un mapa directo. La cascada por
alcance y por origen/destino queda como respaldo para categorias que el modelo todavia no escribe;
si tampoco alcanza, la fila cae en `ETAPA_NO_CLASIFICADA` y el importe se publica en la
reconciliacion. Inventar una etapa "OTROS" esconderia plata.
"""

from __future__ import annotations

ETAPA_NO_CLASIFICADA = "ETAPA_NO_CLASIFICADA"

# Etapas en orden logistico: es el orden del waterfall y de los rankings.
PRODUCCION = "PRODUCCION"
TRANSFERENCIA_PLANTA_DEPOSITO = "TRANSFERENCIA_PLANTA_DEPOSITO"
INGRESO_DEPOSITO = "INGRESO_DEPOSITO"
ALMACENAMIENTO = "ALMACENAMIENTO"
EGRESO_DEPOSITO = "EGRESO_DEPOSITO"
CROSS_DOCK = "CROSS_DOCK"
RETIRO_CONTENEDOR = "RETIRO_CONTENEDOR"
TRANSPORTE_CONTENEDOR = "TRANSPORTE_CONTENEDOR"
CONSOLIDACION = "CONSOLIDACION"
TRANSPORTE_TERMINAL = "TRANSPORTE_TERMINAL"
TERMINAL = "TERMINAL"
THC = "THC"
DESPACHANTE = "DESPACHANTE"
MARITIMO = "MARITIMO"
ESPERA = "ESPERA"
DEMORA = "DEMORA"
PENALIDAD = "PENALIDAD"
OPORTUNIDAD = "OPORTUNIDAD"

ORDEN_ETAPAS = (
    PRODUCCION,
    TRANSFERENCIA_PLANTA_DEPOSITO,
    INGRESO_DEPOSITO,
    ALMACENAMIENTO,
    EGRESO_DEPOSITO,
    CROSS_DOCK,
    RETIRO_CONTENEDOR,
    TRANSPORTE_CONTENEDOR,
    CONSOLIDACION,
    TRANSPORTE_TERMINAL,
    TERMINAL,
    THC,
    DESPACHANTE,
    MARITIMO,
    ESPERA,
    DEMORA,
    PENALIDAD,
    OPORTUNIDAD,
    ETAPA_NO_CLASIFICADA,
)

ETAPA_POR_CATEGORIA = {
    "PRODUCCION": PRODUCCION,
    "FLETE_PRODUCTO": TRANSFERENCIA_PLANTA_DEPOSITO,
    "IN_DEPOSITO": INGRESO_DEPOSITO,
    "ALMACENAMIENTO": ALMACENAMIENTO,
    "OUT_DEPOSITO": EGRESO_DEPOSITO,
    "CROSS_DOCK": CROSS_DOCK,
    "ROUND_TRIP": RETIRO_CONTENEDOR,
    "FLETE_CONTENEDOR": TRANSPORTE_CONTENEDOR,
    "CONSOLIDACION": CONSOLIDACION,
    "FLETE_TERMINAL": TRANSPORTE_TERMINAL,
    "COSTO_TERMINAL": TERMINAL,
    "THC": THC,
    "DESPACHANTE": DESPACHANTE,
    "FLETE_MARITIMO": MARITIMO,
    "ESPERA": ESPERA,
    "DEMORA": DEMORA,
    "PENALIDAD": PENALIDAD,
    "OPORTUNIDAD_FRIO": OPORTUNIDAD,
}

# Respaldo por alcance: solo se usa si la categoria no esta en el mapa.
_ETAPA_POR_ALCANCE = {
    "CONTENEDOR": TRANSPORTE_CONTENEDOR,
    "PEDIDO": PENALIDAD,
}

NODO = "NODO"
ARCO = "ARCO"
GEOGRAFIA_NO_CLASIFICADA = "GEOGRAFIA_NO_CLASIFICADA"


def clasificar_etapa(
    categoria: str,
    alcance: str = "",
    origen: str = "",
    destino: str = "",
) -> str:
    """Devuelve la etapa logistica de un cargo.

    Prioridad: categoria explicita, despues alcance, despues geografia. Un cargo de alcance LOTE que
    se queda en el mismo sitio es almacenamiento; entre dos sitios distintos es una transferencia.
    """
    etapa = ETAPA_POR_CATEGORIA.get((categoria or "").strip().upper())
    if etapa:
        return etapa

    etapa = _ETAPA_POR_ALCANCE.get((alcance or "").strip().upper())
    if etapa:
        return etapa

    geografia = tipo_geografia(origen, destino)
    if geografia == NODO:
        return ALMACENAMIENTO
    if geografia == ARCO:
        return TRANSFERENCIA_PLANTA_DEPOSITO

    return ETAPA_NO_CLASIFICADA


def tipo_geografia(origen: str, destino: str) -> str:
    """Separa costo de nodo de costo de tramo.

    En el paquete real los cinco pares origen-destino mas frecuentes son auto-loops
    (`RUTA9 -> RUTA9` y compania): son costos de almacenamiento en un nodo, no de un arco.
    Mezclarlos deja el ranking de arcos dominado por el deposito y hace imposible preguntar que
    nodo gasta mas.
    """
    origen = (origen or "").strip()
    destino = (destino or "").strip()
    if not origen or not destino:
        return GEOGRAFIA_NO_CLASIFICADA
    return NODO if origen == destino else ARCO


def categorias_de_etapa(etapa: str) -> list[str]:
    """Categorias que caen en una etapa segun el mapa directo."""
    return sorted(c for c, e in ETAPA_POR_CATEGORIA.items() if e == etapa)


def ordenar_por_etapa(filas: list[dict], clave: str = "etapa") -> list[dict]:
    posicion = {etapa: i for i, etapa in enumerate(ORDEN_ETAPAS)}
    return sorted(filas, key=lambda fila: posicion.get(fila[clave], len(posicion)))
