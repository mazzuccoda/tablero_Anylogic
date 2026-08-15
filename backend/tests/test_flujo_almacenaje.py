"""Pruebas del flujo fisico y del almacenaje (MOD v3.3).

Las tres reglas que estas pruebas cuidan son las que el paquete real puso en evidencia: el
almacenaje no puede entrar como arco, los egresos de un deposito no pueden salir de
`egresos_dia_tn` (viene en cero) y un dato que no existe no puede aparecer como cero.
"""

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.core.models import (
    ArcExecution,
    CostCharge,
    InventorySnapshot,
    TipoContable,
)
from apps.dashboard import almacenamiento
from apps.dashboard.cost_explorer import flujo_fisico
from apps.dashboard.cost_explorer.clasificacion import ALMACENAMIENTO, ESPERA, THC
from apps.dashboard.cost_explorer.filtros import FiltrosCostos
from apps.ingest.importadores import importar_kpis_barrido, importar_paquete_auditoria

pytestmark = pytest.mark.django_db

DEPOSITO = "DEPOSITO_SUR"
PLANTA = "PLANTA_NORTE"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def run(paquete):
    return importar_paquete_auditoria(paquete).simulation_run


@pytest.fixture
def caja() -> FiltrosCostos:
    return FiltrosCostos()


def _total_caja(run) -> float:
    return CostCharge.objects.filter(
        simulation_run=run, tipo_contable=TipoContable.CAJA
    ).aggregate(total=Sum("importe_usd"))["total"]


def test_las_etapas_mas_el_almacenaje_cierran_contra_el_total(run, caja):
    """Reconciliacion del bloque A: nada de plata se pierde al separar el almacenaje del flujo."""
    cintas = flujo_fisico.cintas_por_etapa(run, caja)

    total = cintas["costo_etapas_usd"] + cintas["almacenamiento_excluido_usd"]

    assert total == pytest.approx(_total_caja(run))


def test_el_almacenaje_no_aparece_como_etapa_ni_como_cinta(run, caja):
    cintas = flujo_fisico.cintas_por_etapa(run, caja)

    assert ALMACENAMIENTO not in [fila["etapa"] for fila in cintas["etapas"]]
    assert cintas["almacenamiento_excluido_usd"] > 0


def test_una_etapa_sin_cargo_dice_sin_dato_y_no_cero(run, caja):
    """La espera mueve producto y no tiene cargo propio: cero seria afirmar que no costo nada."""
    etapas = flujo_fisico.cintas_por_etapa(run, caja)["etapas"]
    espera = next(fila for fila in etapas if fila["etapa"] == ESPERA)

    assert espera["toneladas"] > 0
    assert espera["costo_usd"] is None
    assert espera["usd_por_tn"] is None


def test_una_etapa_sin_arco_no_inventa_toneladas(run, caja):
    thc = next(
        fila for fila in flujo_fisico.cintas_por_etapa(run, caja)["etapas"] if fila["etapa"] == THC
    )

    assert thc["costo_usd"] > 0
    assert thc["toneladas"] is None
    assert thc["arcos"] == 0


def test_las_cintas_solo_dibujan_producto_entre_sitios_distintos(run, caja):
    """Un auto-loop no es una cinta y el contenedor vacio no mueve producto."""
    cintas = flujo_fisico.cintas_por_etapa(run, caja)

    assert all(fila["origen"] != fila["destino"] for fila in cintas["cintas"])
    assert {fila["tipo_arco"] for fila in cintas["tipos_arco_no_dibujados"]} >= {
        "CARGA_CONSOLIDACION",
        "DESCARGA_TERMINAL",
    }
    assert all(fila["motivo"] for fila in cintas["tipos_arco_no_dibujados"])


def test_los_egresos_del_deposito_salen_de_los_arcos_y_no_de_egresos_dia_tn(run, caja):
    """En el paquete real `egresos_dia_tn` viene en cero en los cinco depositos."""
    InventorySnapshot.objects.filter(simulation_run=run, ubicacion=DEPOSITO).update(
        egresos_dia_tn=0.0
    )
    esperado = (
        ArcExecution.objects.filter(
            simulation_run=run,
            tipo_arco__in=almacenamiento.TIPOS_ARCO_EGRESO,
            origen=DEPOSITO,
        )
        .values_list("toneladas", flat=True)
        .first()
    )

    flujo = almacenamiento.flujo_y_decision(run, DEPOSITO)["flujo"]

    assert esperado > 0
    assert flujo["egresos_tn"] == pytest.approx(esperado)


def test_un_producto_sin_cargo_de_almacenaje_no_figura_en_cero(run, caja):
    CostCharge.objects.filter(
        simulation_run=run, categoria=almacenamiento.CATEGORIA_ALMACENAJE
    ).delete()

    filas = almacenamiento.por_producto(run, caja)["filas"]

    assert filas
    assert all(fila["costo_almacenaje_usd"] is None for fila in filas)
    assert all(fila["porcentaje"] is None for fila in filas)


def test_la_vista_por_producto_no_mezcla_la_planta_con_los_depositos(run, caja):
    """PLANTA guarda producto y no cobra almacenaje: sumarla inflaria stock y dias."""
    stock_planta = (
        InventorySnapshot.objects.filter(simulation_run=run, ubicacion=PLANTA)
        .exclude(stock_fisico_tn=0)
        .exists()
    )
    datos = almacenamiento.por_producto(run, caja)

    assert stock_planta
    assert PLANTA not in datos["depositos"]
    assert datos["depositos"] == [DEPOSITO]


def test_el_costo_por_producto_reconcilia_con_el_total_de_almacenaje(run, caja):
    datos = almacenamiento.por_producto(run, caja)

    suma = sum(fila["costo_almacenaje_usd"] or 0.0 for fila in datos["filas"])

    assert suma == pytest.approx(datos["costo_almacenaje_total_usd"])


def test_la_serie_diaria_trae_la_fecha_calendario(run):
    """MOD v4.1 / ADR-064.2: la corrida de ejemplo arranca el 2026-04-01."""
    datos = almacenamiento.serie_diaria(run, DEPOSITO)

    assert datos["tiene_fecha_calendario"] is True
    primera_fila = datos["serie_diaria"][0]
    assert primera_fila["dia"] == 1
    assert primera_fila["fecha"] == "2026-04-01"


def test_el_stock_promedio_del_deposito_coincide_con_su_serie_diaria(run):
    flujo = almacenamiento.flujo_y_decision(run, DEPOSITO)
    serie = almacenamiento.serie_diaria(run, DEPOSITO)["serie_diaria"]

    promedio = sum(fila["stock_fisico_tn"] for fila in serie) / flujo["dias_de_la_corrida"]

    assert flujo["flujo"]["stock_promedio_tn"] == pytest.approx(promedio)


def test_el_deposito_publica_flujo_costo_y_decision_por_separado(run):
    datos = almacenamiento.flujo_y_decision(run, DEPOSITO)

    assert set(datos) >= {"flujo", "costo", "decision", "productos"}
    assert datos["costo"]["costo_almacenaje_usd"] > 0
    assert datos["decision"]["evaluaciones"] >= 0


def test_el_recorrido_del_lote_ordena_los_arcos_y_separa_el_almacenaje(run):
    id_lote = ArcExecution.objects.filter(simulation_run=run).exclude(id_lote="").first().id_lote

    datos = almacenamiento.recorrido_de_lote(run, id_lote)

    dias = [paso["dia_inicio"] for paso in datos["recorrido"]]
    assert dias == sorted(dias)
    assert all(
        paso["tipo_arco"] != almacenamiento.CATEGORIA_ALMACENAJE for paso in datos["recorrido"]
    )


def test_el_top_de_lotes_ordena_por_costo_y_rechaza_un_orden_inventado(run, caja):
    lotes = almacenamiento.top_lotes(run, caja)["lotes"]

    costos = [fila["costo_almacenaje_usd"] for fila in lotes]
    assert costos == sorted(costos, reverse=True)
    with pytest.raises(almacenamiento.OrdenInvalido):
        almacenamiento.top_lotes(run, caja, "el-que-mas-me-guste")


def test_los_endpoints_nuevos_contestan_contra_el_paquete(run, api):
    rutas = [
        f"/api/v1/simulation-runs/{run.run_id}/costs/cintas/",
        f"/api/v1/simulation-runs/{run.run_id}/almacenamiento/por-producto/",
        f"/api/v1/simulation-runs/{run.run_id}/almacenamiento/depositos/",
        f"/api/v1/simulation-runs/{run.run_id}/almacenamiento/top-lotes/",
        f"/api/v1/simulation-runs/{run.run_id}/depositos/{DEPOSITO}/flujo-y-decision/",
        f"/api/v1/simulation-runs/{run.run_id}/depositos/{DEPOSITO}/stock-diario/",
    ]

    assert [api.get(ruta).status_code for ruta in rutas] == [200] * len(rutas)


def test_un_deposito_que_no_existe_contesta_404_con_los_que_si(run, api):
    respuesta = api.get(
        f"/api/v1/simulation-runs/{run.run_id}/depositos/NO_EXISTE/flujo-y-decision/"
    )

    assert respuesta.status_code == 404
    assert DEPOSITO in respuesta.json()["detalle"]


def test_un_lote_que_no_existe_contesta_404(run, api):
    respuesta = api.get(f"/api/v1/simulation-runs/{run.run_id}/lotes/L-NO-EXISTE/recorrido/")

    assert respuesta.status_code == 404


def test_una_corrida_de_barrido_no_finge_flujo_fisico(kpis_barrido, api):
    """Sin `costos_eventos` ni arcos, la respuesta correcta es 409, no un panel en cero."""
    importar_kpis_barrido(kpis_barrido)

    respuesta = api.get("/api/v1/simulation-runs/E-03-R0/costs/cintas/")

    assert respuesta.status_code == 409
    assert respuesta.json()["tiene_drill_down"] is False
