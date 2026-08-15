"""Pruebas de importacion (MOD v2.0, seccion 11)."""

import json
from datetime import date

import pytest

from apps.core.models import (
    ArcExecution,
    AssignmentResult,
    CostCharge,
    DecisionAlternative,
    EstadoImportacion,
    InventorySnapshot,
    ResourceCapacitySnapshot,
    ScenarioRunKpi,
    SimulationRun,
    TipoCorrida,
)
from apps.ingest.importadores import (
    ImportacionRechazada,
    importar_kpis_barrido,
    importar_paquete_auditoria,
)

pytestmark = pytest.mark.django_db


def test_importa_el_paquete_valido(paquete):
    lote = importar_paquete_auditoria(paquete)

    assert lote.estado == EstadoImportacion.COMPLETADA
    run = SimulationRun.objects.get(run_id="E-00-R0")
    assert run.tipo == TipoCorrida.AUDITORIA
    assert run.nivel_auditoria == "COMPLETA"
    assert run.version_esquema == "ADR-064.2"
    assert DecisionAlternative.objects.filter(simulation_run=run).count() == 5
    assert AssignmentResult.objects.filter(simulation_run=run).count() == 2
    assert ArcExecution.objects.filter(simulation_run=run).count() == 7
    assert CostCharge.objects.filter(simulation_run=run).count() == 9
    assert InventorySnapshot.objects.filter(simulation_run=run).count() == 10
    assert ResourceCapacitySnapshot.objects.filter(simulation_run=run).count() == 15


def test_importa_la_fecha_calendario_de_la_campania(paquete):
    """MOD v4.1 / ADR-064.2: fecha = fecha_inicio_campania + (dia_campania - 1)."""
    importar_paquete_auditoria(paquete)
    run = SimulationRun.objects.get(run_id="E-00-R0")

    assert run.fecha_inicio_campania == date(2026, 4, 1)

    costo_dia_1 = CostCharge.objects.get(id_costo="C-0001")  # dia_campania = 1
    assert costo_dia_1.fecha == date(2026, 4, 1)
    costo_dia_4 = CostCharge.objects.get(id_costo="C-0008")  # dia_campania = 4
    assert costo_dia_4.fecha == date(2026, 4, 4)

    elegida = DecisionAlternative.objects.get(id_alternativa="P-0002-D1-A2")  # dia_campania = 2
    assert elegida.fecha == date(2026, 4, 2)

    arco = ArcExecution.objects.get(id_evento_arco="1")  # dia_inicio = 1.60
    assert arco.fecha_inicio == date(2026, 4, 1)

    asignacion = AssignmentResult.objects.get(id_asignacion="A-0002")  # dia_asignacion = 2.10
    assert asignacion.fecha_asignacion == date(2026, 4, 2)


def test_material_y_proveedor_son_campos_propios_no_extra(paquete):
    """ADR-T05 (MOD v6): declarados en el esquema desde siempre, ahora tienen columna propia en
    vez de caer en `extra` — filtrables en el Cost Explorer."""
    importar_paquete_auditoria(paquete)

    costo = CostCharge.objects.get(id_costo="C-0001")
    assert costo.material == "MAT_UREA"
    assert costo.proveedor == "PROVEEDOR_1"
    assert "material" not in costo.extra
    assert "proveedor" not in costo.extra

    asignacion = AssignmentResult.objects.get(id_asignacion="A-0002")
    assert asignacion.material == "MAT_MAP"
    assert "material" not in asignacion.extra


def test_la_migracion_de_datos_promueve_material_y_proveedor_desde_extra(paquete):
    """ADR-T05: una corrida importada antes de este cambio tiene material/proveedor solo en
    `extra` (import viejo). La migracion de datos los copia a la columna nueva sin reimportar
    nada — se prueba simulando ese estado viejo sobre una corrida ya importada."""
    import importlib

    from django.apps import apps as app_registry

    importar_paquete_auditoria(paquete)

    costo = CostCharge.objects.get(id_costo="C-0001")
    costo.extra = {**costo.extra, "material": costo.material, "proveedor": costo.proveedor}
    costo.material = ""
    costo.proveedor = ""
    costo.save()

    asignacion = AssignmentResult.objects.get(id_asignacion="A-0002")
    asignacion.extra = {**asignacion.extra, "material": asignacion.material}
    asignacion.material = ""
    asignacion.save()

    migracion = importlib.import_module("apps.core.migrations.0004_material_proveedor_adr_t05")
    migracion._promover_desde_extra(app_registry, None)

    costo.refresh_from_db()
    assert costo.material == "MAT_UREA"
    assert costo.proveedor == "PROVEEDOR_1"

    asignacion.refresh_from_db()
    assert asignacion.material == "MAT_MAP"


def test_una_tabla_que_no_declara_fecha_la_deja_en_none(carpeta_ejemplo):
    """Una tabla sin la columna en su esquema no inventa una fecha: queda None (ADR-T01)."""
    from tests.conftest import empaquetar

    esquema = json.loads((carpeta_ejemplo / "esquema_auditoria.json").read_text())
    tabla_costos = next(t for t in esquema["tablas"] if t["tabla"] == "costos_eventos")
    tabla_costos["columnas"] = [c for c in tabla_costos["columnas"] if c != "fecha"]

    lineas_costos = (carpeta_ejemplo / "costos_eventos.csv").read_text().splitlines()
    sin_fecha = [",".join(f.split(",")[:-1]) for f in lineas_costos]  # fecha es la ultima columna

    importar_paquete_auditoria(
        empaquetar(
            carpeta_ejemplo,
            {
                "esquema_auditoria.json": json.dumps(esquema).encode(),
                "costos_eventos.csv": ("\n".join(sin_fecha) + "\n").encode(),
            },
        )
    )

    run = SimulationRun.objects.get(run_id="E-00-R0")
    # El resto del paquete si declara fecha_inicio_campania: no se ve afectado por el recorte de
    # una sola tabla.
    assert run.fecha_inicio_campania == date(2026, 4, 1)
    assert CostCharge.objects.get(id_costo="C-0001").fecha is None
    assert DecisionAlternative.objects.get(id_alternativa="P-0002-D1-A2").fecha == date(2026, 4, 2)


def test_guarda_las_columnas_sin_campo_propio_en_extra(paquete):
    importar_paquete_auditoria(paquete)
    alternativa = DecisionAlternative.objects.get(id_alternativa="P-0001-D1-A2")

    assert alternativa.extra["politica_seleccion"] == "COSTO_INCREMENTAL"
    assert alternativa.extra["horas_ciclo_fisico_total"] == "18.0"


def test_un_vacio_no_es_cero(paquete):
    importar_paquete_auditoria(paquete)
    no_factible = DecisionAlternative.objects.get(id_alternativa="P-0002-D1-A1")

    # La alternativa descartada por cupo no informa holgura: el modelo no la produce.
    assert no_factible.holgura_estimada_dias is None
    assert no_factible.llega_a_tiempo_estimado is None


def test_espera_sin_techo_fisico_conserva_la_duracion_negativa(paquete):
    importar_paquete_auditoria(paquete)
    espera = ArcExecution.objects.get(tipo_arco="ESPERA_PORTACONTENEDOR")

    assert espera.duracion_esperada_horas == -1.0
    assert espera.duracion_esperada_aplica is False


def test_rechaza_un_paquete_sin_esquema(carpeta_ejemplo):
    from tests.conftest import empaquetar

    with pytest.raises(ImportacionRechazada) as error:
        importar_paquete_auditoria(empaquetar(carpeta_ejemplo, quitar=("esquema_auditoria.json",)))

    assert "esquema_auditoria.json" in str(error.value)


def test_rechaza_un_archivo_zip_invalido():
    with pytest.raises(ImportacionRechazada) as error:
        importar_paquete_auditoria(b"esto no es un zip")

    assert "ZIP valido" in str(error.value)


def test_rechaza_una_columna_faltante(carpeta_ejemplo):
    from tests.conftest import empaquetar

    original = (carpeta_ejemplo / "costos_eventos.csv").read_text().splitlines()
    encabezado = original[0].replace("tipo_contable,", "")
    filas = [",".join(f.split(",")[:6] + f.split(",")[7:]) for f in original[1:]]
    mutado = "\n".join([encabezado, *filas]).encode()

    with pytest.raises(ImportacionRechazada) as error:
        importar_paquete_auditoria(empaquetar(carpeta_ejemplo, {"costos_eventos.csv": mutado}))

    assert "tipo_contable" in str(error.value)


def test_version_de_esquema_desconocida_deja_advertencia(carpeta_ejemplo):
    from tests.conftest import empaquetar

    esquema = json.loads((carpeta_ejemplo / "esquema_auditoria.json").read_text())
    esquema["version_esquema"] = "ADR-064.9"
    mutado = json.dumps(esquema).encode()

    lote = importar_paquete_auditoria(
        empaquetar(carpeta_ejemplo, {"esquema_auditoria.json": mutado})
    )

    assert lote.estado == EstadoImportacion.COMPLETADA_CON_ADVERTENCIAS
    assert any("ADR-064.9" in m["texto"] for m in lote.advertencias)


def test_conteo_distinto_del_manifiesto_deja_advertencia(carpeta_ejemplo):
    from tests.conftest import empaquetar

    manifiesto = json.loads(
        (carpeta_ejemplo / "manifiesto_auditoria_E-00-R0.json").read_text()
    )
    manifiesto["tablas"]["costos_eventos"]["filas"] = 99
    mutado = json.dumps(manifiesto).encode()

    lote = importar_paquete_auditoria(
        empaquetar(carpeta_ejemplo, {"manifiesto_auditoria_E-00-R0.json": mutado})
    )

    assert lote.estado == EstadoImportacion.COMPLETADA_CON_ADVERTENCIAS
    assert any("99 filas" in m["texto"] for m in lote.advertencias)


def test_descuadre_de_inventario_deja_advertencia(carpeta_ejemplo):
    from tests.conftest import empaquetar

    lineas = (carpeta_ejemplo / "snapshot_inventario.csv").read_text().splitlines()
    indice = lineas[0].split(",").index("descuadre_tn")
    columnas = lineas[1].split(",")
    columnas[indice] = "2.5"
    lineas[1] = ",".join(columnas)
    mutado = ("\n".join(lineas) + "\n").encode()

    lote = importar_paquete_auditoria(
        empaquetar(carpeta_ejemplo, {"snapshot_inventario.csv": mutado})
    )

    assert any("descuadre_tn" in m["texto"] for m in lote.advertencias)


def test_reimportar_la_misma_corrida_no_duplica(paquete):
    importar_paquete_auditoria(paquete)
    importar_paquete_auditoria(paquete)

    assert SimulationRun.objects.filter(run_id="E-00-R0").count() == 1
    assert DecisionAlternative.objects.filter(simulation_run__run_id="E-00-R0").count() == 5


def test_importa_el_barrido(kpis_barrido):
    lote = importar_kpis_barrido(kpis_barrido)

    assert lote.filas_por_tabla["kpis_por_corrida"] == 4
    corrida = SimulationRun.objects.get(run_id="E-03-R1")
    assert corrida.tipo == TipoCorrida.BARRIDO
    assert corrida.tiene_drill_down is False
    assert ScenarioRunKpi.objects.get(simulation_run=corrida).valores["nivel_servicio"] == 0.988


def test_el_barrido_no_degrada_una_corrida_ya_auditada(paquete, kpis_barrido):
    # kpis_por_corrida.csv trae E-00 replica 0, o sea el mismo run_id del paquete auditado.
    importar_paquete_auditoria(paquete)

    lote = importar_kpis_barrido(kpis_barrido)

    run = SimulationRun.objects.get(run_id="E-00-R0")
    assert run.tipo == TipoCorrida.AUDITORIA
    assert run.tiene_drill_down is True
    assert DecisionAlternative.objects.filter(simulation_run=run).count() == 5
    assert ScenarioRunKpi.objects.get(simulation_run=run).valores["nivel_servicio"] == 0.97
    assert lote.estado == EstadoImportacion.COMPLETADA
    assert any("se conservo el drill-down" in m["texto"] for m in lote.mensajes)


def test_el_paquete_auditado_promueve_una_corrida_ya_cargada_por_el_barrido(paquete, kpis_barrido):
    importar_kpis_barrido(kpis_barrido)

    importar_paquete_auditoria(paquete)

    run = SimulationRun.objects.get(run_id="E-00-R0")
    assert run.tipo == TipoCorrida.AUDITORIA
    assert run.tiene_drill_down is True
    assert ScenarioRunKpi.objects.get(simulation_run=run).valores["nivel_servicio"] == 0.97


def test_rechaza_un_barrido_sin_columnas_de_identidad():
    with pytest.raises(ImportacionRechazada):
        importar_kpis_barrido(b"costo_total_usd,nivel_servicio\n100,0.9\n")


def test_importa_un_paquete_con_la_clave_declarada_repetida(carpeta_ejemplo):
    from tests.conftest import empaquetar

    # Los paquetes reales repiten id_alternativa: el modelo reusa el id_decision cuando reevalua
    # el mismo pedido otro dia. Las filas son eventos distintos y tienen que entrar todas.
    lineas = (carpeta_ejemplo / "decisiones_alternativas.csv").read_text().splitlines()
    repetida = lineas[1].encode()
    mutado = ("\n".join([*lineas, lineas[1]]) + "\n").encode()

    lote = importar_paquete_auditoria(
        empaquetar(carpeta_ejemplo, {"decisiones_alternativas.csv": mutado})
    )

    run = SimulationRun.objects.get(run_id="E-00-R0")
    id_repetido = repetida.decode().split(",")[esquema_columna_id_alternativa(carpeta_ejemplo)]
    assert DecisionAlternative.objects.filter(simulation_run=run).count() == 6
    assert (
        DecisionAlternative.objects.filter(
            simulation_run=run, id_alternativa=id_repetido
        ).count()
        == 2
    )
    assert any("se repite" in m["texto"] for m in lote.advertencias)


def esquema_columna_id_alternativa(carpeta) -> int:
    encabezado = (carpeta / "decisiones_alternativas.csv").read_text().splitlines()[0]
    return encabezado.split(",").index("id_alternativa")


def test_avisa_de_los_archivos_que_el_esquema_no_declara(carpeta_ejemplo):
    from tests.conftest import empaquetar

    lote = importar_paquete_auditoria(
        empaquetar(carpeta_ejemplo, {"asignaciones_capacidad.csv": b"a,b\n1,2\n"})
    )

    assert any("no se importaron" in m["texto"] for m in lote.mensajes)
