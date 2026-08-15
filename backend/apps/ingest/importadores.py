"""Importacion de un paquete de auditoria y de un barrido (MOD v2.0, secciones 4 y 10).

La importacion es sincrona y transaccional: el volumen de una carga manual de una corrida se
resuelve en segundos y no justifica Celery en esta version (ADR-T02).
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass, field

from django.db import transaction

from apps.core.models import (
    ArcExecution,
    AssignmentResult,
    CostCharge,
    DecisionAlternative,
    EstadoImportacion,
    ImportBatch,
    ImportedFile,
    InventorySnapshot,
    NivelAuditoria,
    Project,
    ResourceCapacitySnapshot,
    Scenario,
    ScenarioRunKpi,
    SimulationRun,
    TipoCorrida,
)

from .esquema import (
    TABLAS_OBLIGATORIAS,
    VERSION_ESQUEMA_CONOCIDA,
    EsquemaInvalido,
    Manifiesto,
    leer_esquema,
    leer_manifiesto,
    validar_columnas,
)
from .valores import booleano, entero, fecha, flotante, texto

PROYECTO_POR_DEFECTO = "Red logistica Argentina 2026"

ERROR = "ERROR"
ADVERTENCIA = "ADVERTENCIA"
INFO = "INFO"


class ImportacionRechazada(Exception):
    """Error critico: el paquete no se importa (MOD v2.0, seccion 10)."""

    def __init__(self, mensajes: list[dict]):
        super().__init__("; ".join(m["texto"] for m in mensajes))
        self.mensajes = mensajes


@dataclass
class Resultado:
    simulation_run: SimulationRun | None = None
    estado: str = EstadoImportacion.COMPLETADA
    mensajes: list[dict] = field(default_factory=list)
    filas_por_tabla: dict[str, int] = field(default_factory=dict)


def _mensaje(nivel: str, texto_mensaje: str, **detalle) -> dict:
    return {"nivel": nivel, "texto": texto_mensaje, **detalle}


def _checksum(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _filas(contenido: bytes) -> tuple[list[str], list[dict[str, str]]]:
    texto_csv = contenido.decode("utf-8-sig")
    lector = csv.reader(io.StringIO(texto_csv))
    try:
        encabezado = next(lector)
    except StopIteration:
        return [], []
    encabezado = [c.strip() for c in encabezado]
    # strict=False: una fila con menos celdas deja esos campos ausentes, que se leen como vacios,
    # en vez de romper la importacion entera.
    filas = [
        dict(zip(encabezado, fila, strict=False))
        for fila in lector
        if any(c.strip() for c in fila)
    ]
    return encabezado, filas


# --- Mapeo de columnas a campos ------------------------------------------------------------

T, F, E, B, D = texto, flotante, entero, booleano, fecha

MAPEOS: dict[str, tuple[type, dict[str, tuple[str, object]]]] = {
    "decisiones_alternativas": (
        DecisionAlternative,
        {
            "id_decision": ("id_decision", T),
            "ronda": ("ronda", E),
            "id_alternativa": ("id_alternativa", T),
            "codigo_pedido": ("codigo_pedido", T),
            "producto": ("producto", T),
            "circuito": ("circuito", T),
            "origen_stock": ("origen_stock", T),
            "destino_final": ("destino_final", T),
            "factible": ("factible", B),
            "orden_ranking": ("orden_ranking", E),
            "resultado_ejecucion": ("resultado_ejecucion", T),
            "codigo_motivo": ("codigo_motivo", T),
            "detalle_motivo": ("detalle_motivo", T),
            "costo_incremental_usd_tn": ("costo_incremental_usd_tn", F),
            "costo_end_to_end_usd_tn": ("costo_end_to_end_usd_tn", F),
            "es_mas_barata_no_factible": ("es_mas_barata_no_factible", B),
            "holgura_estimada_dias": ("holgura_estimada_dias", F),
            "llega_a_tiempo_estimado": ("llega_a_tiempo_estimado", B),
            "toneladas_solicitadas": ("toneladas_solicitadas", F),
            "toneladas_factibles": ("toneladas_factibles", F),
            "toneladas_tomadas": ("toneladas_tomadas", F),
            "dia_simulacion": ("dia_simulacion", F),
            "fecha": ("fecha", D),
            "fecha_cutoff": ("fecha_cutoff", D),
        },
    ),
    "asignaciones_elegidas": (
        AssignmentResult,
        {
            "id_asignacion": ("id_asignacion", T),
            "id_decision": ("id_decision", T),
            "id_alternativa": ("id_alternativa", T),
            "codigo_pedido": ("codigo_pedido", T),
            "producto": ("producto", T),
            "origen": ("origen", T),
            "circuito": ("circuito", T),
            "dia_asignacion": ("dia_asignacion", F),
            "dia_ultima_entrega": ("dia_ultima_entrega", F),
            "toneladas_asignadas": ("toneladas_asignadas", F),
            "toneladas_entregadas": ("toneladas_entregadas", F),
            "contenedores_creados": ("contenedores_creados", E),
            "contenedores_entregados": ("contenedores_entregados", E),
            "costo_incremental_estimado": ("costo_incremental_estimado", F),
            "costo_real_contenedores_usd": ("costo_real_contenedores_usd", F),
            "desvio_costo_usd": ("desvio_costo_usd", F),
            "dias_ciclo_real": ("dias_ciclo_real", F),
            "cerrada": ("cerrada", B),
            "cancelada": ("cancelada", B),
            "motivo_asignacion": ("motivo_asignacion", T),
            "fecha_asignacion": ("fecha_asignacion", D),
        },
    ),
    "ejecucion_arcos": (
        ArcExecution,
        {
            "id_evento_arco": ("id_evento_arco", T),
            "id_decision": ("id_decision", T),
            "id_alternativa": ("id_alternativa", T),
            "id_asignacion": ("id_asignacion", T),
            "id_envio": ("id_envio", T),
            "id_contenedor": ("id_contenedor", T),
            "id_lote": ("id_lote", T),
            "codigo_pedido": ("codigo_pedido", T),
            "producto": ("producto", T),
            "tipo_arco": ("tipo_arco", T),
            "origen": ("origen", T),
            "destino": ("destino", T),
            "toneladas": ("toneladas", F),
            "contenedores": ("contenedores", E),
            "dia_inicio": ("dia_inicio", F),
            "dia_fin": ("dia_fin", F),
            "duracion_real_horas": ("duracion_real_horas", F),
            "duracion_esperada_horas": ("duracion_esperada_horas", F),
            "recurso_utilizado": ("recurso_utilizado", T),
            "estado_final": ("estado_final", T),
            "fecha_inicio": ("fecha_inicio", D),
            "fecha_fin": ("fecha_fin", D),
        },
    ),
    "costos_eventos": (
        CostCharge,
        {
            "id_costo": ("id_costo", T),
            "dia": ("dia", F),
            "dia_campania": ("dia_campania", E),
            "fecha": ("fecha", D),
            "tipo_contable": ("tipo_contable", T),
            "categoria": ("categoria", T),
            "codigo_pedido": ("codigo_pedido", T),
            "id_asignacion": ("id_asignacion", T),
            "id_decision": ("id_decision", T),
            "id_contenedor": ("id_contenedor", T),
            "id_lote": ("id_lote", T),
            "producto": ("producto", T),
            "circuito": ("circuito", T),
            "origen": ("origen", T),
            "destino": ("destino", T),
            "sitio": ("sitio", T),
            "unidad": ("unidad", T),
            "cantidad": ("cantidad", F),
            "tarifa": ("tarifa", F),
            "importe_usd": ("importe_usd", F),
            "alcance": ("alcance", T),
            "es_incremental": ("es_incremental", B),
            "motivo": ("motivo", T),
        },
    ),
    "snapshot_inventario": (
        InventorySnapshot,
        {
            "dia": ("dia", E),
            "fecha": ("fecha", D),
            "ubicacion": ("ubicacion", T),
            "tipo_ubicacion": ("tipo_ubicacion", T),
            "producto": ("producto", T),
            "capacidad_tn": ("capacidad_tn", F),
            "stock_inicial_dia_tn": ("stock_inicial_dia_tn", F),
            "stock_fisico_tn": ("stock_fisico_tn", F),
            "stock_libre_tn": ("stock_libre_tn", F),
            "ingresos_dia_tn": ("ingresos_dia_tn", F),
            "egresos_dia_tn": ("egresos_dia_tn", F),
            "produccion_dia_tn": ("produccion_dia_tn", F),
            "ocupacion_pct": ("ocupacion_pct", F),
            "lotes_abiertos": ("lotes_abiertos", E),
            "lote_mas_antiguo_dias": ("lote_mas_antiguo_dias", F),
            "descuadre_tn": ("descuadre_tn", F),
        },
    ),
    "snapshot_capacidad_recursos": (
        ResourceCapacitySnapshot,
        {
            "dia": ("dia", E),
            "fecha": ("fecha", D),
            "tipo_recurso": ("tipo_recurso", T),
            "ubicacion": ("ubicacion", T),
            "capacidad_nominal": ("capacidad_nominal", F),
            "reservada": ("reservada", F),
            "consumida": ("consumida", F),
            "liberada": ("liberada", F),
            "ocupada": ("ocupada", F),
            "libre": ("libre", F),
            "cola": ("cola", F),
        },
    ),
}

CAMPOS_NO_NULOS = {
    "snapshot_inventario": ("dia", "ubicacion", "producto"),
    "snapshot_capacidad_recursos": ("dia", "tipo_recurso", "ubicacion"),
}


def _instancia(tabla: str, run: SimulationRun, fila: dict[str, str]):
    modelo, mapeo = MAPEOS[tabla]
    campos: dict[str, object] = {}
    for columna, (campo, conversor) in mapeo.items():
        campos[campo] = conversor(fila.get(columna))
    usadas = set(mapeo) | {"run_id", "escenario", "replica"}
    extra = {c: v for c, v in fila.items() if c not in usadas and texto(v) != ""}
    return modelo(simulation_run=run, extra=extra, **campos)


# --- Paquete de auditoria ------------------------------------------------------------------


def _abrir_paquete(contenido: bytes) -> dict[str, bytes]:
    """Devuelve {nombre de archivo (sin carpeta): contenido} de un zip de resultados."""
    archivos: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                nombre = info.filename.rsplit("/", 1)[-1]
                if nombre.startswith("."):
                    continue
                archivos[nombre] = zf.read(info)
    except zipfile.BadZipFile as exc:
        raise ImportacionRechazada(
            [_mensaje(ERROR, "el archivo subido no es un ZIP valido")]
        ) from exc
    return archivos


def importar_paquete_auditoria(contenido_zip: bytes, nombre_paquete: str = "paquete.zip"):
    archivos = _abrir_paquete(contenido_zip)
    mensajes: list[dict] = []

    if "esquema_auditoria.json" not in archivos:
        raise ImportacionRechazada(
            [_mensaje(ERROR, "el paquete no trae esquema_auditoria.json (MOD v2.0 seccion 5.1)")]
        )

    try:
        esquema = leer_esquema(archivos["esquema_auditoria.json"])
    except EsquemaInvalido as exc:
        raise ImportacionRechazada([_mensaje(ERROR, str(exc))]) from exc

    manifiestos = [n for n in archivos if n.startswith("manifiesto_auditoria_")]
    if not manifiestos:
        raise ImportacionRechazada(
            [_mensaje(ERROR, "el paquete no trae manifiesto_auditoria_<run_id>.json")]
        )
    try:
        manifiesto = leer_manifiesto(archivos[manifiestos[0]])
    except EsquemaInvalido as exc:
        raise ImportacionRechazada([_mensaje(ERROR, str(exc))]) from exc

    if esquema.version_esquema != VERSION_ESQUEMA_CONOCIDA:
        mensajes.append(
            _mensaje(
                ADVERTENCIA,
                f"version_esquema {esquema.version_esquema} distinta de la ultima conocida "
                f"{VERSION_ESQUEMA_CONOCIDA}: las columnas pueden no significar lo mismo",
            )
        )

    faltantes = [t for t in TABLAS_OBLIGATORIAS if t not in esquema.tablas]
    if faltantes:
        raise ImportacionRechazada(
            [_mensaje(ERROR, f"el esquema no declara las tablas {', '.join(faltantes)}")]
        )

    errores_estructura: list[dict] = []
    contenidos: dict[str, tuple[bytes, list[dict[str, str]]]] = {}

    for nombre_tabla in TABLAS_OBLIGATORIAS:
        tabla = esquema.tablas[nombre_tabla]
        if tabla.archivo not in archivos:
            errores_estructura.append(
                _mensaje(ERROR, f"falta el archivo {tabla.archivo} declarado en el esquema")
            )
            continue
        crudo = archivos[tabla.archivo]
        encabezado, filas = _filas(crudo)
        for error in validar_columnas(tabla, encabezado):
            errores_estructura.append(_mensaje(ERROR, error))
        mensajes.extend(_avisos_de_claves_repetidas(tabla, filas))
        contenidos[nombre_tabla] = (crudo, filas)

    if errores_estructura:
        raise ImportacionRechazada(errores_estructura)

    declarados = {t.archivo for t in esquema.tablas.values()}
    ignorados = sorted(
        n
        for n in archivos
        if n not in declarados
        and n != "esquema_auditoria.json"
        and not n.startswith("manifiesto_auditoria_")
    )
    if ignorados:
        mensajes.append(
            _mensaje(
                INFO,
                f"el paquete trae archivos que el esquema no declara y no se importaron: "
                f"{', '.join(ignorados)}",
            )
        )

    return _grabar_auditoria(esquema, manifiesto, contenidos, mensajes, nombre_paquete)


def _avisos_de_claves_repetidas(tabla, filas: list[dict[str, str]]) -> list[dict]:
    """Avisa si la clave que declara el esquema se repite dentro de la corrida.

    Pasa en paquetes reales: el modelo reutiliza un `id_decision` cuando reevalua el mismo pedido
    otro dia, asi que `id_alternativa` se repite. Las filas son eventos distintos y se importan
    todas; lo que no puede es quedar en silencio, porque cualquier conteo por clave miente.
    """
    columnas = [c for c in tabla.clave if c != "run_id"]
    if not columnas or not filas:
        return []

    vistas: set[tuple[str, ...]] = set()
    repetidas: set[tuple[str, ...]] = set()
    for fila in filas:
        valor = tuple(texto(fila.get(c)) for c in columnas)
        if valor in vistas:
            repetidas.add(valor)
        else:
            vistas.add(valor)

    if not repetidas:
        return []

    ejemplo = "/".join(sorted(repetidas)[0])
    return [
        _mensaje(
            ADVERTENCIA,
            f"{tabla.archivo}: la clave {', '.join(columnas)} que declara el esquema se repite en "
            f"{len(repetidas)} casos (por ejemplo {ejemplo}); se importaron todas las filas",
            tabla=tabla.tabla,
        )
    ]


@transaction.atomic
def _grabar_auditoria(esquema, manifiesto: Manifiesto, contenidos, mensajes, nombre_paquete):
    run_id = manifiesto.run_id or _run_id_de_filas(contenidos)
    if not run_id:
        raise ImportacionRechazada([_mensaje(ERROR, "no se pudo determinar el run_id del paquete")])

    escenario_codigo = manifiesto.escenario or run_id.split("-R")[0]
    proyecto, _ = Project.objects.get_or_create(nombre=PROYECTO_POR_DEFECTO)
    scenario, _ = Scenario.objects.get_or_create(project=proyecto, codigo=escenario_codigo)

    ya_existia = SimulationRun.objects.filter(run_id=run_id).exists()
    run, _ = SimulationRun.objects.update_or_create(
        run_id=run_id,
        defaults={
            "scenario": scenario,
            "replica": manifiesto.replica,
            "tipo": TipoCorrida.AUDITORIA,
            "nivel_auditoria": manifiesto.nivel_auditoria or NivelAuditoria.COMPLETA,
            "version_esquema": esquema.version_esquema,
            "duracion_campania_dias": manifiesto.duracion_campania_dias,
            "fecha_inicio_campania": fecha(manifiesto.fecha_inicio_campania),
            "generado": manifiesto.generado,
        },
    )

    if ya_existia:
        # Idempotencia: reimportar la misma corrida la reemplaza, no la duplica.
        mensajes.append(_mensaje(INFO, f"la corrida {run_id} ya estaba importada y se reemplazo"))
        for modelo, _mapeo in MAPEOS.values():
            modelo.objects.filter(simulation_run=run).delete()

    lote = ImportBatch.objects.create(
        simulation_run=run, version_esquema=esquema.version_esquema, mensajes=[]
    )

    filas_por_tabla: dict[str, int] = {}

    for nombre_tabla, (crudo, filas) in contenidos.items():
        modelo, _mapeo = MAPEOS[nombre_tabla]
        obligatorios = CAMPOS_NO_NULOS.get(nombre_tabla, ())
        instancias = []
        for fila in filas:
            instancia = _instancia(nombre_tabla, run, fila)
            if any(getattr(instancia, campo) in (None, "") for campo in obligatorios):
                mensajes.append(
                    _mensaje(
                        ADVERTENCIA,
                        f"{nombre_tabla}: fila sin clave completa, se omitio",
                        tabla=nombre_tabla,
                    )
                )
                continue
            instancias.append(instancia)

        modelo.objects.bulk_create(instancias, batch_size=1000)
        filas_por_tabla[nombre_tabla] = len(instancias)

        esperadas = manifiesto.filas_por_tabla.get(nombre_tabla)
        if esperadas is not None and esperadas >= 0 and esperadas != len(instancias):
            mensajes.append(
                _mensaje(
                    ADVERTENCIA,
                    f"{nombre_tabla}: el manifiesto declara {esperadas} filas y se importaron "
                    f"{len(instancias)}",
                    tabla=nombre_tabla,
                )
            )

        ImportedFile.objects.create(
            import_batch=lote,
            nombre=esquema.tablas[nombre_tabla].archivo,
            tabla=nombre_tabla,
            checksum_sha256=_checksum(crudo),
            filas_importadas=len(instancias),
            filas_manifiesto=esperadas,
        )

    descuadradas = (
        InventorySnapshot.objects.filter(simulation_run=run)
        .exclude(descuadre_tn=0)
        .exclude(descuadre_tn__isnull=True)
        .count()
    )
    if descuadradas:
        mensajes.append(
            _mensaje(
                ADVERTENCIA,
                f"snapshot_inventario: {descuadradas} filas con descuadre_tn distinto de cero "
                "(C-12 exige cero): revisar la calidad del paquete",
                tabla="snapshot_inventario",
            )
        )

    lote.mensajes = mensajes
    lote.filas_por_tabla = filas_por_tabla
    lote.estado = (
        EstadoImportacion.COMPLETADA_CON_ADVERTENCIAS
        if any(m["nivel"] == ADVERTENCIA for m in mensajes)
        else EstadoImportacion.COMPLETADA
    )
    lote.save(update_fields=["mensajes", "filas_por_tabla", "estado"])
    return lote


def _run_id_de_filas(contenidos) -> str:
    for _crudo, filas in contenidos.values():
        for fila in filas:
            if texto(fila.get("run_id")):
                return texto(fila["run_id"])
    return ""


# --- Barrido -------------------------------------------------------------------------------

COLUMNAS_IDENTIDAD_BARRIDO = ("version_modelo", "id_escenario", "replica", "semilla")


@transaction.atomic
def importar_kpis_barrido(contenido_csv: bytes, nombre_archivo: str = "kpis_por_corrida.csv"):
    encabezado, filas = _filas(contenido_csv)
    faltantes = [c for c in COLUMNAS_IDENTIDAD_BARRIDO if c not in encabezado]
    if faltantes:
        raise ImportacionRechazada(
            [
                _mensaje(
                    ERROR,
                    f"{nombre_archivo}: faltan las columnas de identidad "
                    f"{', '.join(faltantes)}",
                )
            ]
        )
    if not filas:
        raise ImportacionRechazada([_mensaje(ERROR, f"{nombre_archivo} no trae filas")])

    columnas_kpi = [c for c in encabezado if c not in COLUMNAS_IDENTIDAD_BARRIDO]
    proyecto, _ = Project.objects.get_or_create(nombre=PROYECTO_POR_DEFECTO)

    mensajes: list[dict] = []
    lote = ImportBatch.objects.create(mensajes=[])
    importadas = 0

    for fila in filas:
        escenario_codigo = texto(fila.get("id_escenario"))
        replica = entero(fila.get("replica"))
        if not escenario_codigo or replica is None:
            mensajes.append(_mensaje(ADVERTENCIA, "fila sin id_escenario o replica, se omitio"))
            continue

        run_id = f"{escenario_codigo}-R{replica}"
        scenario, _ = Scenario.objects.get_or_create(project=proyecto, codigo=escenario_codigo)
        defaults = {
            "scenario": scenario,
            "replica": replica,
            "tipo": TipoCorrida.BARRIDO,
            "nivel_auditoria": NivelAuditoria.DESACTIVADA,
            "version_modelo": texto(fila.get("version_modelo")),
        }
        auditada = SimulationRun.objects.filter(
            run_id=run_id, tipo=TipoCorrida.AUDITORIA
        ).first()
        if auditada is not None:
            # El barrido incluye la corrida que ademas se audito: sus KPIs enriquecen el tablero,
            # pero degradarla a BARRIDO borraria el drill-down de unas tablas que si estan.
            del defaults["tipo"], defaults["nivel_auditoria"]
            mensajes.append(
                _mensaje(
                    INFO,
                    f"{run_id} ya estaba importada como corrida auditada: se le agregaron los "
                    "KPIs del barrido y se conservo el drill-down",
                )
            )
        run, _ = SimulationRun.objects.update_or_create(run_id=run_id, defaults=defaults)
        valores = {c: flotante(fila.get(c)) for c in columnas_kpi}
        ScenarioRunKpi.objects.update_or_create(
            simulation_run=run,
            defaults={"semilla": entero(fila.get("semilla")), "valores": valores},
        )
        importadas += 1

    ImportedFile.objects.create(
        import_batch=lote,
        nombre=nombre_archivo,
        tabla="kpis_por_corrida",
        checksum_sha256=_checksum(contenido_csv),
        filas_importadas=importadas,
    )

    lote.filas_por_tabla = {"kpis_por_corrida": importadas}
    lote.mensajes = mensajes
    lote.estado = (
        EstadoImportacion.COMPLETADA_CON_ADVERTENCIAS
        if any(m["nivel"] == ADVERTENCIA for m in mensajes)
        else EstadoImportacion.COMPLETADA
    )
    lote.save(update_fields=["mensajes", "filas_por_tabla", "estado"])
    return lote
