"""Lectura y validacion del esquema que publica AnyLogic.

El contrato de datos es `esquema_auditoria.json` + `manifiesto_auditoria_<run_id>.json`
(MOD v2.0 seccion 5.1, ADR-T01). Este modulo no define columnas: las lee del paquete.
Lo unico que el backend recuerda es la ultima `version_esquema` conocida, para poder avisar
cuando llega otra en vez de asumir que las columnas significan lo mismo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

VERSION_ESQUEMA_CONOCIDA = "ADR-064.2"

# Nombre de tabla -> archivo esperado. Coincide con `escribirEsquemaAuditoria()` del modelo.
ARCHIVO_POR_TABLA = {
    "decisiones_alternativas": "decisiones_alternativas.csv",
    "asignaciones_elegidas": "asignaciones_elegidas.csv",
    "ejecucion_arcos": "ejecucion_arcos.csv",
    "costos_eventos": "costos_eventos.csv",
    "snapshot_inventario": "snapshot_inventario.csv",
    "snapshot_capacidad_recursos": "capacidad_por_dia.csv",
}

TABLAS_OBLIGATORIAS = tuple(ARCHIVO_POR_TABLA)


class EsquemaInvalido(Exception):
    """El paquete no trae un `esquema_auditoria.json` utilizable."""


@dataclass
class TablaEsquema:
    tabla: str
    archivo: str
    clave: list[str]
    columnas: list[str]


@dataclass
class Esquema:
    version_esquema: str
    tablas: dict[str, TablaEsquema] = field(default_factory=dict)

    def tabla_de_archivo(self, archivo: str) -> TablaEsquema | None:
        for t in self.tablas.values():
            if t.archivo == archivo:
                return t
        return None


def leer_esquema(contenido: bytes | str) -> Esquema:
    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise EsquemaInvalido(f"esquema_auditoria.json no es JSON valido: {exc}") from exc

    version = datos.get("version_esquema")
    if not version:
        raise EsquemaInvalido("esquema_auditoria.json no declara version_esquema")

    tablas: dict[str, TablaEsquema] = {}
    for entrada in datos.get("tablas", []):
        nombre = entrada.get("tabla")
        columnas = entrada.get("columnas") or []
        if not nombre or not columnas:
            raise EsquemaInvalido(f"tabla sin nombre o sin columnas en el esquema: {entrada!r}")
        tablas[nombre] = TablaEsquema(
            tabla=nombre,
            archivo=entrada.get("archivo") or ARCHIVO_POR_TABLA.get(nombre, f"{nombre}.csv"),
            clave=entrada.get("clave") or [],
            columnas=list(columnas),
        )

    if not tablas:
        raise EsquemaInvalido("esquema_auditoria.json no declara ninguna tabla")

    return Esquema(version_esquema=version, tablas=tablas)


@dataclass
class Manifiesto:
    run_id: str
    version_esquema: str
    escenario: str
    replica: int | None
    nivel_auditoria: str
    duracion_campania_dias: int | None
    # ADR-064.2 (MOD v4.1): ancla de calendario del dia 1 de campania, "YYYY-MM-DD". Un
    # manifiesto de una version anterior no la trae y queda None.
    fecha_inicio_campania: str | None
    generado: str
    filas_por_tabla: dict[str, int]


def leer_manifiesto(contenido: bytes | str) -> Manifiesto:
    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise EsquemaInvalido(f"el manifiesto no es JSON valido: {exc}") from exc

    filas: dict[str, int] = {}
    for tabla, detalle in (datos.get("tablas") or {}).items():
        if isinstance(detalle, dict) and detalle.get("filas") is not None:
            filas[tabla] = int(detalle["filas"])

    return Manifiesto(
        run_id=datos.get("run_id", ""),
        version_esquema=datos.get("version_esquema", ""),
        escenario=datos.get("escenario", ""),
        replica=datos.get("replica"),
        nivel_auditoria=datos.get("nivel_auditoria", ""),
        duracion_campania_dias=datos.get("duracion_campania_dias"),
        fecha_inicio_campania=datos.get("fecha_inicio_campania"),
        generado=datos.get("generado", ""),
        filas_por_tabla=filas,
    )


def validar_columnas(tabla: TablaEsquema, encabezado: list[str]) -> list[str]:
    """Devuelve los errores de estructura del CSV contra el esquema publicado."""
    errores: list[str] = []
    faltantes = [c for c in tabla.columnas if c not in encabezado]
    sobrantes = [c for c in encabezado if c not in tabla.columnas]

    if faltantes:
        errores.append(f"{tabla.archivo}: faltan columnas {', '.join(faltantes)}")
    if sobrantes:
        errores.append(f"{tabla.archivo}: columnas no declaradas en el esquema "
                       f"{', '.join(sobrantes)}")
    return errores
