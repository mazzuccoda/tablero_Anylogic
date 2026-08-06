"""Flujo fisico de la red: cuantas toneladas paso por cada etapa y cuanto costo esa etapa.

Tres decisiones que valen la pena leer antes de tocar este modulo:

- **El almacenaje no es un arco.** `ejecucion_arcos` solo registra movimientos; el almacenaje
  vive en `costos_eventos` con `categoria = ALMACENAMIENTO`. Un flujo armado desde los arcos lo
  excluye por
  construccion, asi que se publica aparte (`almacenamiento_excluido_usd`) y no se pierde.
- **El costo de la etapa no se une por id contra los arcos.** Un cargo de contenedor (THC, terminal,
  despachante) matchea cuatro o cinco arcos de ese mismo contenedor: unir por `id_contenedor`
  multiplicaria el importe. Las toneladas salen de los arcos y el importe de `costos_eventos`
  clasificado por `categoria`, que es el mismo mapa que usa el waterfall. Asi la suma de las etapas
  mas el almacenaje cierra contra el total de la corrida.
- **Hay etapas sin arco y arcos sin etapa de costo.** THC o despachante no mueven producto (no
  tienen arco: `toneladas = null`), y las esperas mueven producto sin cargo propio
  (`costo_usd = null`). Ninguno de los dos casos se rellena con cero: son "sin dato" distintos.
"""

from __future__ import annotations

from django.db.models import Count, Sum

from apps.core.models import ArcExecution, CostCharge, SimulationRun

from .clasificacion import (
    ALMACENAMIENTO,
    CONSOLIDACION,
    CROSS_DOCK,
    ESPERA,
    ETAPA_NO_CLASIFICADA,
    RETIRO_CONTENEDOR,
    TERMINAL,
    TRANSFERENCIA_PLANTA_DEPOSITO,
    TRANSPORTE_TERMINAL,
    clasificar_etapa,
)
from .filtros import FiltrosCostos

CONSOLIDACION_EN_TERMINAL = "CONSOLIDACION_TERMINAL"
TRANSFERENCIA_DEPOSITO_DEPOSITO = "TRANSFERENCIA_DEPOSITO_DEPOSITO"
DESCARGA_TERMINAL = "DESCARGA_TERMINAL"

# `tipo_arco` -> etapa fisica. Los diez tipos declarados por ADR-064; el paquete real trae nueve
# (nunca aparecio `DEPOSITO_DEPOSITO`). Las dos esperas caen en la misma etapa porque son el mismo
# hecho fisico (el producto quiere avanzar y no puede), y las dos consolidaciones quedan separadas
# porque ocurren en sitios distintos del circuito y el cargo de consolidacion es solo el de origen.
ETAPA_POR_TIPO_ARCO = {
    "PLANTA_DEPOSITO": TRANSFERENCIA_PLANTA_DEPOSITO,
    "DEPOSITO_DEPOSITO": TRANSFERENCIA_DEPOSITO_DEPOSITO,
    "CROSS_DOCK": CROSS_DOCK,
    "TERMINAL_ORIGEN_CONTENEDOR_VACIO": RETIRO_CONTENEDOR,
    "ESPERA_PORTACONTENEDOR": ESPERA,
    "ESPERA_POSICION": ESPERA,
    "CARGA_CONSOLIDACION": CONSOLIDACION,
    "ORIGEN_TERMINAL_CONTENEDOR_CARGADO": TRANSPORTE_TERMINAL,
    "DESCARGA_TERMINAL": DESCARGA_TERMINAL,
    "CONSOLIDACION_TERMINAL": CONSOLIDACION_EN_TERMINAL,
}

# Secuencia fisica real: planta -> deposito -> retiro y consolidacion -> terminal. Es el orden del
# sankey y de la tabla; `ORDEN_ETAPAS` de `clasificacion` no alcanza porque no conoce las etapas que
# solo existen como arco (descarga y consolidacion en terminal).
SECUENCIA = (
    TRANSFERENCIA_PLANTA_DEPOSITO,
    TRANSFERENCIA_DEPOSITO_DEPOSITO,
    CROSS_DOCK,
    RETIRO_CONTENEDOR,
    ESPERA,
    CONSOLIDACION,
    TRANSPORTE_TERMINAL,
    DESCARGA_TERMINAL,
    CONSOLIDACION_EN_TERMINAL,
    TERMINAL,
)

# Campos del recorte que tambien existen como columna de `ejecucion_arcos`.
CAMPOS_DE_ARCO = ("producto", "origen", "destino", "codigo_pedido", "id_contenedor", "id_lote")

# Arcos que mueven producto de un sitio a otro: son los unicos que se dibujan como cinta.
TIPOS_ARCO_DE_PRODUCTO = (
    "PLANTA_DEPOSITO",
    "DEPOSITO_DEPOSITO",
    "CROSS_DOCK",
    "ORIGEN_TERMINAL_CONTENEDOR_CARGADO",
)

NOTA_ALMACENAJE = (
    "el almacenaje no es un arco: no aparece en las cintas y se publica aparte "
    "(ADR-064 seccion 5.3, MOD v3.3 bloque B)"
)


def etapa_de_arco(tipo_arco: str) -> str:
    return ETAPA_POR_TIPO_ARCO.get((tipo_arco or "").strip().upper(), ETAPA_NO_CLASIFICADA)


def _posicion(etapa: str) -> int:
    return SECUENCIA.index(etapa) if etapa in SECUENCIA else len(SECUENCIA)


def _arcos_filtrados(run: SimulationRun, filtros: FiltrosCostos):
    arcos = ArcExecution.objects.filter(simulation_run=run)
    for campo, valor in filtros.exactos.items():
        if campo in CAMPOS_DE_ARCO:
            arcos = arcos.filter(**{campo: valor})
    if filtros.dia_desde is not None:
        arcos = arcos.filter(dia_inicio__gte=filtros.dia_desde)
    if filtros.dia_hasta is not None:
        arcos = arcos.filter(dia_inicio__lte=filtros.dia_hasta)
    return arcos


def toneladas_por_etapa(run: SimulationRun, filtros: FiltrosCostos) -> dict[str, dict]:
    """Toneladas y cantidad de arcos por etapa fisica.

    De los filtros de costos solo se pueden trasladar los que existen como columna de
    `ejecucion_arcos`; el resto se ignora aca y queda declarado en `filtros_ignorados`.
    """
    arcos = _arcos_filtrados(run, filtros)
    por_etapa: dict[str, dict] = {}
    consulta = arcos.values("tipo_arco").annotate(toneladas=Sum("toneladas"), arcos=Count("id"))
    for fila in consulta:
        etapa = etapa_de_arco(fila["tipo_arco"])
        datos = por_etapa.setdefault(etapa, {"toneladas": 0.0, "arcos": 0, "tipos_arco": []})
        datos["toneladas"] += fila["toneladas"] or 0.0
        datos["arcos"] += fila["arcos"]
        datos["tipos_arco"].append(fila["tipo_arco"])
    for datos in por_etapa.values():
        datos["tipos_arco"] = sorted(datos["tipos_arco"])
    return por_etapa


def cintas_entre_sitios(
    run: SimulationRun, filtros: FiltrosCostos
) -> tuple[list[dict], list[dict]]:
    """Cintas de producto entre sitios: planta -> deposito -> terminal.

    Solo se dibujan los arcos que mueven producto entre dos sitios distintos. Quedan afuera, con su
    tonelaje declarado en `tipos_arco_no_dibujados`:

    - los arcos de nodo (`CARGA_CONSOLIDACION`, `DESCARGA_TERMINAL`, `CONSOLIDACION_TERMINAL`,
      `ESPERA_POSICION`), que son auto-loops: pasan dentro de un sitio y un auto-loop en un sankey
      no significa nada;
    - el retiro de contenedores vacios y la espera de portacontenedor, que van de la terminal al
      deposito: no mueven producto y, dibujados, crearian un ciclo `deposito -> terminal ->
      deposito` que el sankey no puede representar.
    """
    consulta = (
        _arcos_filtrados(run, filtros)
        .exclude(origen="")
        .exclude(destino="")
        .values("tipo_arco", "origen", "destino", "producto")
        .annotate(toneladas=Sum("toneladas"), arcos=Count("id"))
    )
    cintas: dict[tuple[str, str, str], dict] = {}
    no_dibujados: dict[str, dict] = {}
    for fila in consulta:
        tipo = fila["tipo_arco"]
        mueve_producto = tipo in TIPOS_ARCO_DE_PRODUCTO and fila["origen"] != fila["destino"]
        if not mueve_producto:
            resumen = no_dibujados.setdefault(
                tipo, {"tipo_arco": tipo, "toneladas": 0.0, "arcos": 0, "motivo": _motivo(fila)}
            )
            resumen["toneladas"] += fila["toneladas"] or 0.0
            resumen["arcos"] += fila["arcos"]
            continue
        clave = (fila["origen"], fila["destino"], fila["producto"])
        cinta = cintas.setdefault(
            clave,
            {
                "origen": fila["origen"],
                "destino": fila["destino"],
                "producto": fila["producto"],
                "toneladas": 0.0,
                "arcos": 0,
                "tipos_arco": [],
            },
        )
        cinta["toneladas"] += fila["toneladas"] or 0.0
        cinta["arcos"] += fila["arcos"]
        cinta["tipos_arco"].append(tipo)
        cinta["etapa"] = etapa_de_arco(tipo)

    filas = sorted(cintas.values(), key=lambda fila: -fila["toneladas"])
    for fila in filas:
        fila["tipos_arco"] = sorted(set(fila["tipos_arco"]))
    return filas, sorted(no_dibujados.values(), key=lambda fila: -fila["toneladas"])


def _motivo(fila: dict) -> str:
    if fila["origen"] == fila["destino"]:
        return f"arco de nodo ({fila['origen']} -> {fila['destino']}): pasa dentro del sitio"
    return "no mueve producto entre sitios (contenedor vacio o espera)"


def _costo_por_etapa(run: SimulationRun, filtros: FiltrosCostos) -> dict[str, dict]:
    cargos = filtros.aplicar(CostCharge.objects.filter(simulation_run=run))
    consulta = cargos.values("categoria", "alcance", "origen", "destino").annotate(
        importe=Sum("importe_usd"), eventos=Count("id")
    )
    por_etapa: dict[str, dict] = {}
    for fila in consulta:
        etapa = clasificar_etapa(
            fila["categoria"], fila["alcance"], fila["origen"], fila["destino"]
        )
        datos = por_etapa.setdefault(etapa, {"importe_usd": 0.0, "eventos": 0, "categorias": set()})
        datos["importe_usd"] += fila["importe"] or 0.0
        datos["eventos"] += fila["eventos"]
        if fila["categoria"]:
            datos["categorias"].add(fila["categoria"])
    return por_etapa


def cintas_por_etapa(run: SimulationRun, filtros: FiltrosCostos) -> dict:
    """Etapas fisicas con sus toneladas y su costo, mas las cintas para el sankey."""
    toneladas = toneladas_por_etapa(run, filtros)
    costos = _costo_por_etapa(run, filtros)

    etapas = []
    for etapa in sorted({*toneladas, *costos} - {ALMACENAMIENTO}, key=_posicion):
        fisico = toneladas.get(etapa)
        contable = costos.get(etapa)
        tn = fisico["toneladas"] if fisico else None
        usd = contable["importe_usd"] if contable else None
        etapas.append(
            {
                "etapa": etapa,
                "toneladas": tn,
                "arcos": fisico["arcos"] if fisico else 0,
                "tipos_arco": fisico["tipos_arco"] if fisico else [],
                "costo_usd": usd,
                "eventos": contable["eventos"] if contable else 0,
                "categorias": sorted(contable["categorias"]) if contable else [],
                "usd_por_tn": usd / tn if usd is not None and tn else None,
            }
        )

    con_toneladas = [fila for fila in etapas if fila["toneladas"]]
    cintas, no_dibujados = cintas_entre_sitios(run, filtros)
    sitios = sorted({fila["origen"] for fila in cintas} | {fila["destino"] for fila in cintas})

    almacenamiento = costos.get(ALMACENAMIENTO)
    return {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "filtros_aplicados": filtros.como_dict(),
        "filtros_ignorados_en_arcos": sorted(
            campo for campo in filtros.exactos if campo not in CAMPOS_DE_ARCO
        ),
        "etapas": etapas,
        "nodos": [{"id": sitio} for sitio in sitios],
        "cintas": cintas,
        "etapas_con_toneladas": [
            {"etapa": fila["etapa"], "toneladas": fila["toneladas"]} for fila in con_toneladas
        ],
        "base_cintas": (
            "cada cinta son las toneladas de producto que ejecucion_arcos movio entre dos sitios; "
            "los arcos de nodo y los movimientos de contenedor vacio no se dibujan y su tonelaje "
            "queda declarado en tipos_arco_no_dibujados"
        ),
        "tipos_arco_no_dibujados": no_dibujados,
        "toneladas_entregadas": toneladas.get(DESCARGA_TERMINAL, {}).get("toneladas"),
        "costo_etapas_usd": sum(fila["costo_usd"] or 0.0 for fila in etapas),
        "almacenamiento_excluido_usd": almacenamiento["importe_usd"] if almacenamiento else None,
        "almacenamiento_eventos": almacenamiento["eventos"] if almacenamiento else 0,
        "nota": NOTA_ALMACENAJE,
    }
