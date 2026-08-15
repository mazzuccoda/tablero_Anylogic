"""Pruebas de los endpoints del MVP (MOD v2.0, secciones 9 y 12)."""

import pytest
from rest_framework.test import APIClient

from apps.ingest.importadores import importar_kpis_barrido, importar_paquete_auditoria

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def corrida_importada(paquete):
    return importar_paquete_auditoria(paquete).simulation_run


def test_dashboard_suma_solo_los_cargos_de_caja(api, corrida_importada):
    respuesta = api.get("/api/v1/simulation-runs/E-00-R0/dashboard/")
    datos = respuesta.json()

    assert respuesta.status_code == 200
    # 6000 + 25000 + 3800 + 1800 + 3600 + 14160 + 2280 + 540; el ECONOMICO queda afuera.
    assert datos["costos"]["costo_total_caja_usd"] == pytest.approx(57180.0)
    assert datos["costos"]["costo_total_economico_usd"] == pytest.approx(3500.0)
    assert datos["costos"]["costo_usd_tn"] == pytest.approx(57180.0 / 775.0)


def test_dashboard_trae_la_fecha_de_inicio_de_campania(api, corrida_importada):
    datos = api.get("/api/v1/simulation-runs/E-00-R0/dashboard/").json()

    assert datos["fecha_inicio_campania"] == "2026-04-01"
    assert datos["inventario"]["agrupado_por"] == "dia"
    assert datos["inventario"]["tiene_fecha_calendario"] is True
    assert datos["inventario"]["serie"][0]["periodo"] == "2026-04-01"


def test_dashboard_agrupa_el_inventario_por_mes(api, corrida_importada):
    # La corrida de ejemplo dura 5 dias (abril de 2026): agrupados por mes queda un solo periodo.
    datos = api.get(
        "/api/v1/simulation-runs/E-00-R0/dashboard/", {"agrupar_por": "mes"}
    ).json()

    assert datos["inventario"]["agrupado_por"] == "mes"
    serie = datos["inventario"]["serie"]
    assert len(serie) == 1
    assert serie[0]["periodo"] == "2026-04"
    assert serie[0]["dias"] == 5


def test_dashboard_rechaza_una_agrupacion_desconocida(api, corrida_importada):
    respuesta = api.get(
        "/api/v1/simulation-runs/E-00-R0/dashboard/", {"agrupar_por": "trimestre"}
    )

    assert respuesta.status_code == 400
    assert "trimestre" in respuesta.json()["detalle"]


def test_dashboard_informa_la_restriccion(api, corrida_importada):
    restriccion = api.get("/api/v1/simulation-runs/E-00-R0/dashboard/").json()["restriccion"]

    assert restriccion["mas_baratas_no_factibles"] == 2
    assert restriccion["pedidos_con_alternativa_mas_barata_no_factible"] == 2
    motivos = {m["codigo_motivo"]: m["alternativas"] for m in restriccion["por_motivo"]}
    assert motivos == {"SIN_CAPACIDAD_ANTES_CUTOFF": 1, "SIN_CUPO_CROSS_DOCK": 1}
    esperas = {e["tipo_arco"]: e["espera_promedio_horas"] for e in restriccion["esperas"]}
    assert esperas["ESPERA_PORTACONTENEDOR"] == pytest.approx(12.0)
    assert esperas["ESPERA_POSICION"] == pytest.approx(16.8)


def test_por_que_arma_la_union_completa(api, corrida_importada):
    respuesta = api.get("/api/v1/orders/P-0001/why/", {"run_id": "E-00-R0"})
    datos = respuesta.json()

    assert respuesta.status_code == 200
    assert len(datos["decisiones"]) == 2
    assert len(datos["asignaciones"]) == 1
    assert len(datos["arcos"]) == 3
    assert datos["resumen"]["hay_mas_barata_no_factible"] is True
    # La elegida costo 91 usd/tn y la mas barata no factible 84: la restriccion costo 7.
    assert datos["resumen"]["sobrecosto_de_la_restriccion_usd_tn"] == pytest.approx(7.0)
    assert datos["resumen"]["costo_caja_usd"] == pytest.approx(36600.0)


def test_por_que_avisa_cuando_la_corrida_es_de_barrido(api, kpis_barrido):
    importar_kpis_barrido(kpis_barrido)

    respuesta = api.get("/api/v1/orders/P-0001/why/", {"run_id": "E-03-R0"})

    assert respuesta.status_code == 409
    assert respuesta.json()["tiene_drill_down"] is False
    assert "DESACTIVADA" in respuesta.json()["detalle"]


def test_por_que_exige_run_id(api, corrida_importada):
    assert api.get("/api/v1/orders/P-0001/why/").status_code == 400


def test_dashboard_de_barrido_explica_que_no_hay_drill_down(api, kpis_barrido):
    importar_kpis_barrido(kpis_barrido)

    datos = api.get("/api/v1/simulation-runs/E-00-R1/dashboard/").json()

    assert datos["tiene_drill_down"] is False
    assert "DESACTIVADA" in datos["motivo_sin_drill_down"]
    assert datos["kpis_barrido"]["nivel_servicio"] == 0.965


def test_comparacion_de_dos_corridas(api, kpis_barrido):
    importar_kpis_barrido(kpis_barrido)

    datos = api.post(
        "/api/v1/comparisons/", {"run_a": "E-00-R0", "run_b": "E-03-R0"}, format="json"
    ).json()

    servicio = next(k for k in datos["kpis"] if k["kpi"] == "nivel_servicio")
    assert servicio["a"] == 0.97
    assert servicio["b"] == 0.99
    assert servicio["diferencia"] == pytest.approx(0.02)
    assert servicio["variacion_pct"] == pytest.approx(100 * 0.02 / 0.97)


def test_exportacion_csv_filtrada(api, corrida_importada):
    respuesta = api.get(
        "/api/v1/simulation-runs/E-00-R0/export/costos/", {"tipo_contable": "CAJA"}
    )

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "text/csv"
    lineas = respuesta.content.decode().strip().splitlines()
    assert lineas[0].startswith("id,id_costo") or "id_costo" in lineas[0]
    assert len(lineas) == 9  # 8 cargos de caja + encabezado


def test_upload_rechaza_un_paquete_invalido(api, carpeta_ejemplo):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.conftest import empaquetar

    contenido = empaquetar(carpeta_ejemplo, quitar=("manifiesto_auditoria_E-00-R0.json",))
    archivo = SimpleUploadedFile("paquete.zip", contenido, content_type="application/zip")

    respuesta = api.post("/api/v1/imports/upload/", {"archivo": archivo}, format="multipart")

    assert respuesta.status_code == 422
    assert respuesta.json()["estado"] == "RECHAZADA"


def test_upload_importa_el_paquete(api, paquete):
    from django.core.files.uploadedfile import SimpleUploadedFile

    archivo = SimpleUploadedFile("paquete.zip", paquete, content_type="application/zip")

    respuesta = api.post("/api/v1/imports/upload/", {"archivo": archivo}, format="multipart")

    assert respuesta.status_code == 201
    assert respuesta.json()["run_id"] == "E-00-R0"
    assert respuesta.json()["estado"] == "COMPLETADA"


def test_listado_de_corridas(api, corrida_importada):
    datos = api.get("/api/v1/simulation-runs/").json()

    assert datos["count"] == 1
    assert datos["results"][0]["run_id"] == "E-00-R0"
    assert datos["results"][0]["tiene_drill_down"] is True
