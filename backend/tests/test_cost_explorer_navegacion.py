"""Pruebas de los niveles de navegacion del Cost Explorer (MOD v3.2, PR-02).

Desgloses por dimension, nodo/arco, objeto de costo, eventos paginados y sobrecosto por restriccion.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.models import DecisionAlternative
from apps.dashboard.cost_explorer import FiltrosCostos
from apps.dashboard.cost_explorer.dimensiones import (
    DimensionInvalida,
    costos_por_arco,
    costos_por_dimension,
    resumen_nodo_arco,
    waterfall,
)
from apps.dashboard.cost_explorer.eventos import LIMITE_MAXIMO
from apps.dashboard.cost_explorer.restricciones import (
    sobrecosto_por_decision,
    sobrecosto_por_restriccion,
)
from apps.ingest.importadores import importar_kpis_barrido, importar_paquete_auditoria

pytestmark = pytest.mark.django_db

CAJA_TOTAL = 57180.0
BASE = "/api/v1/simulation-runs/E-00-R0/cost-explorer"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def run(paquete):
    return importar_paquete_auditoria(paquete).simulation_run


@pytest.fixture
def caja() -> FiltrosCostos:
    return FiltrosCostos()


def test_el_desglose_por_dimension_suma_el_total(run, caja):
    for dimension in ("producto", "circuito", "sitio", "unidad"):
        filas = costos_por_dimension(run, caja, dimension)
        assert sum(fila["importe_usd"] for fila in filas) == pytest.approx(CAJA_TOTAL)
        assert sum(fila["porcentaje"] for fila in filas) == pytest.approx(100.0)


def test_una_dimension_fuera_de_la_lista_blanca_no_llega_al_orm(run, caja):
    with pytest.raises(DimensionInvalida):
        costos_por_dimension(run, caja, "importe_usd")


def test_un_par_origen_igual_destino_es_nodo_y_no_arco(run, caja):
    filas = costos_por_arco(run, caja)
    resumen = resumen_nodo_arco(filas)

    assert {fila["tipo"] for fila in filas} <= {"NODO", "ARCO", "GEOGRAFIA_NO_CLASIFICADA"}
    assert resumen["nodo_usd"] > 0
    assert resumen["nodo_usd"] + resumen["arco_usd"] == pytest.approx(
        sum(fila["importe_usd"] for fila in filas)
    )


def test_el_waterfall_acumula_hasta_el_total(run, caja):
    cascada = waterfall(run, caja)
    pasos = cascada["pasos"]

    assert pasos[0]["base"] == 0
    for anterior, siguiente in zip(pasos, pasos[1:], strict=False):
        assert siguiente["base"] == pytest.approx(anterior["acumulado"])
    assert pasos[-1]["acumulado"] == pytest.approx(CAJA_TOTAL)
    assert cascada["total_usd"] == pytest.approx(CAJA_TOTAL)


def test_el_costo_por_objeto_declara_la_base_fisica_de_cada_usd_tn(api, run):
    for objeto, clave in (
        ("lote", "id_lote"),
        ("contenedor", "id_contenedor"),
        ("pedido", "codigo_pedido"),
    ):
        datos = api.get(f"{BASE}/by-object/{objeto}/").json()

        assert datos["clave"] == clave
        assert datos["base"]
        for fila in datos["filas"]:
            if fila["toneladas"]:
                assert fila["usd_por_tn"] == pytest.approx(
                    fila["importe_usd"] / fila["toneladas"]
                )
            else:
                assert fila["usd_por_tn"] is None


def test_un_objeto_sin_toneladas_no_inventa_un_usd_tn_de_cero(api, run):
    datos = api.get(f"{BASE}/by-object/lote/").json()

    sin_base = [fila for fila in datos["filas"] if fila["toneladas"] is None]
    assert all(fila["usd_por_tn"] is None for fila in sin_base)
    assert datos["objetos_sin_toneladas"] == len(sin_base)


def test_un_objeto_de_costo_inventado_se_rechaza(api, run):
    respuesta = api.get(f"{BASE}/by-object/camion/")

    assert respuesta.status_code == 400
    assert "objeto de costo desconocido" in respuesta.json()["detalle"]


def test_los_eventos_vienen_paginados_y_con_su_etapa(api, run):
    datos = api.get(f"{BASE}/events/", {"limit": "2"}).json()

    assert datos["total"] > len(datos["filas"])
    assert len(datos["filas"]) == 2
    assert datos["filas"][0]["importe_usd"] >= datos["filas"][1]["importe_usd"]
    assert datos["filas"][0]["etapa"]
    assert datos["filas"][0]["geografia"] in {"NODO", "ARCO", "GEOGRAFIA_NO_CLASIFICADA"}


def test_los_eventos_no_dejan_pedir_la_corrida_entera(api, run):
    respuesta = api.get(f"{BASE}/events/", {"limit": str(LIMITE_MAXIMO + 1)})

    assert respuesta.status_code == 400
    assert "exportacion CSV" in respuesta.json()["detalle"]


def test_un_orden_de_eventos_inventado_se_rechaza(api, run):
    respuesta = api.get(f"{BASE}/events/", {"orden": "importe_usd desc"})

    assert respuesta.status_code == 400


def test_el_corrimiento_de_eventos_no_repite_filas(api, run):
    primera = api.get(f"{BASE}/events/", {"limit": "3", "offset": "0"}).json()
    segunda = api.get(f"{BASE}/events/", {"limit": "3", "offset": "3"}).json()

    ids = {fila["id_costo"] for fila in primera["filas"]}
    assert ids.isdisjoint({fila["id_costo"] for fila in segunda["filas"]})


def test_el_sobrecosto_de_la_restriccion_compara_la_elegida_con_la_bloqueada(run):
    filas = sobrecosto_por_decision(run)

    por_decision = {fila["id_decision"]: fila for fila in filas}
    caso = por_decision["P-0001-D1"]
    assert caso["codigo_motivo"] == "SIN_CAPACIDAD_ANTES_CUTOFF"
    assert caso["costo_elegida_usd_tn"] == pytest.approx(91.0)
    assert caso["costo_sin_restriccion_usd_tn"] == pytest.approx(84.0)
    assert caso["sobrecosto_usd_tn"] == pytest.approx(7.0)
    assert caso["sobrecosto_usd"] == pytest.approx(7.0 * 500.0)


def test_el_sobrecosto_se_agrega_por_restriccion(run):
    datos = sobrecosto_por_restriccion(run)

    motivos = {fila["codigo_motivo"]: fila for fila in datos["por_restriccion"]}
    assert motivos["SIN_CAPACIDAD_ANTES_CUTOFF"]["decisiones"] == 1
    assert motivos["SIN_CAPACIDAD_ANTES_CUTOFF"]["sobrecosto_usd_tn"] == pytest.approx(7.0)
    assert datos["sobrecosto_total_usd"] == pytest.approx(
        sum(fila["sobrecosto_usd"] for fila in datos["decisiones"])
    )


def test_el_sobrecosto_del_pedido_coincide_con_el_del_por_que(run):
    """Dos pantallas a un clic de distancia no pueden valorizar la misma restriccion distinto.

    En el paquete real `costo_incremental_usd_tn` viene vacio y el par de costos vive en `extra`,
    asi que las dos vistas comparten los helpers de `restricciones` en vez de leer un campo cada
    una por su cuenta.
    """
    fila = next(f for f in sobrecosto_por_decision(run) if f["codigo_pedido"] == "P-0001")
    porque = APIClient().get("/api/v1/orders/P-0001/why/", {"run_id": "E-00-R0"}).json()

    assert porque["resumen"]["sobrecosto_de_la_restriccion_usd_tn"] == pytest.approx(
        fila["sobrecosto_usd_tn"]
    )


def test_el_por_que_valoriza_la_restriccion_aunque_el_costo_venga_en_extra(run):
    """El paquete real deja el campo vacio y publica el numero en `extra`."""
    alternativa = DecisionAlternative.objects.filter(
        simulation_run=run, es_mas_barata_no_factible=True, codigo_pedido="P-0001"
    ).first()
    alternativa.extra = dict(alternativa.extra, costo_unitario_sin_restriccion="70.0")
    alternativa.costo_incremental_usd_tn = None
    alternativa.save(update_fields=["extra", "costo_incremental_usd_tn"])

    porque = APIClient().get("/api/v1/orders/P-0001/why/", {"run_id": "E-00-R0"}).json()

    assert porque["resumen"]["sobrecosto_de_la_restriccion_usd_tn"] == pytest.approx(91.0 - 70.0)


def test_el_sobrecosto_no_se_mezcla_con_los_importes_de_costos_eventos(api, run):
    """Es un contrafactual: no puede aparecer en ningun total de la reconciliacion."""
    restricciones = api.get(f"{BASE}/constraints/").json()
    reconciliacion = api.get(f"{BASE}/reconciliation/").json()

    assert restricciones["sobrecosto_total_usd"] > 0
    assert reconciliacion["total_usd"] == pytest.approx(CAJA_TOTAL)


def test_los_desgloses_informan_las_filas_consideradas(api, run):
    for ruta in ("by-stage/", "by-category/", "by-dimension/producto/", "by-arc/"):
        datos = api.get(f"{BASE}/{ruta}").json()

        assert datos["importe_considerado"] == pytest.approx(CAJA_TOTAL)
        assert datos["filas_consideradas"] > 0


def test_un_valor_de_filtro_que_no_existe_devuelve_el_recorte_vacio(api, run):
    """No es un error: la API valida el nombre del campo, no el valor.

    Lo importante es que se pueda distinguir "no hay filas" de "el costo es cero": el desglose
    devuelve `filas_consideradas = 0` e `importe_considerado = None`, no un total de 0.
    """
    datos = api.get(f"{BASE}/by-dimension/producto/", {"producto": "NO_EXISTE"}).json()

    assert datos["filas"] == []
    assert datos["filas_consideradas"] == 0
    assert datos["importe_considerado"] is None


def test_los_niveles_nuevos_tambien_contestan_409_en_un_barrido(api, kpis_barrido):
    importar_kpis_barrido(kpis_barrido)
    base_barrido = "/api/v1/simulation-runs/E-03-R0/cost-explorer"

    for ruta in ("waterfall/", "by-arc/", "by-dimension/producto/", "by-object/pedido/",
                 "events/", "constraints/"):
        respuesta = api.get(f"{base_barrido}/{ruta}")
        assert respuesta.status_code == 409, ruta
