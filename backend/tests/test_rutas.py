"""Pruebas de ADR-T06 (ruta fisica derivada) y precio x volumen (MOD v6)."""

import pytest
from rest_framework.test import APIClient

from apps.dashboard.cost_explorer.agregados import costos_por_categoria_con_cantidad
from apps.dashboard.cost_explorer.filtros import FiltrosCostos
from apps.dashboard.cost_explorer.rutas import SIN_RUTA, costos_por_ruta, costos_por_ruta_y_etapa
from apps.ingest.importadores import importar_paquete_auditoria

pytestmark = pytest.mark.django_db

CAJA_TOTAL = 57180.0


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def run(paquete):
    return importar_paquete_auditoria(paquete).simulation_run


@pytest.fixture
def caja() -> FiltrosCostos:
    return FiltrosCostos()


def test_la_ruta_encadena_los_sitios_reales_no_el_tipo_de_circuito(run, caja):
    """A-0001 pasa por PLANTA_NORTE y TERMINAL_BAHIA (con un auto-loop de consolidacion en cada
    punta, que no debe duplicar el sitio); A-0002 por DEPOSITO_SUR y TERMINAL_BAHIA, saltando las
    dos esperas (no son un sitio nuevo)."""
    filas = {f["ruta"]: f for f in costos_por_ruta(run, caja)}

    assert "PLANTA_NORTE→TERMINAL_BAHIA" in filas
    assert "DEPOSITO_SUR→TERMINAL_BAHIA" in filas
    # el tipo de circuito (CIRCUITO_PLANTA/CIRCUITO_DEPOSITO) no aparece como nombre de ruta
    assert not any("CIRCUITO" in ruta for ruta in filas)


def test_el_costo_sin_asignacion_no_se_pierde(run, caja):
    """ALMACENAMIENTO (C-0008) no tiene id_asignacion: cae en SIN_RUTA, no se descarta — la suma
    de todas las rutas sigue cerrando contra el total de caja."""
    filas = costos_por_ruta(run, caja)
    por_ruta = {f["ruta"]: f for f in filas}

    assert SIN_RUTA in por_ruta
    assert por_ruta[SIN_RUTA]["importe_usd"] == 540.0

    assert sum(f["importe_usd"] or 0.0 for f in filas) == CAJA_TOTAL


def test_las_toneladas_por_ruta_salen_de_las_asignaciones(run, caja):
    filas = {f["ruta"]: f for f in costos_por_ruta(run, caja)}

    assert filas["PLANTA_NORTE→TERMINAL_BAHIA"]["toneladas"] == 500.0
    assert filas["DEPOSITO_SUR→TERMINAL_BAHIA"]["toneladas"] == 300.0
    # SIN_RUTA no tiene asignacion propia (viene de un cargo sin id_asignacion), asi que no
    # deberia sumar toneladas de ninguna asignacion real
    assert filas[SIN_RUTA]["toneladas"] is None


def test_el_filtro_por_material_recorta_costo_y_toneladas_igual(run):
    filtros = FiltrosCostos(exactos={"material": "MAT_UREA"})
    filas = costos_por_ruta(run, filtros)

    rutas = {f["ruta"] for f in filas}
    assert rutas == {"PLANTA_NORTE→TERMINAL_BAHIA"}
    assert filas[0]["importe_usd"] == 36600.0  # C-0001..C-0004
    assert filas[0]["toneladas"] == 500.0


def test_la_matriz_etapa_x_ruta_cierra_contra_el_total(run, caja):
    """Cada ruta se abre en las mismas etapas que el waterfall (OUT_DEPOSITO->EGRESO_DEPOSITO,
    FLETE_CONTENEDOR->TRANSPORTE_CONTENEDOR, THC->THC, COSTO_TERMINAL->TERMINAL), y la suma de
    toda la matriz sigue cerrando contra el total de caja."""
    celdas = costos_por_ruta_y_etapa(run, caja)
    assert sum(f["importe_usd"] or 0.0 for f in celdas) == CAJA_TOTAL

    por_ruta_etapa = {(f["ruta"], f["etapa"]): f["importe_usd"] for f in celdas}
    # C-0001: OUT_DEPOSITO 6000 en la ruta de A-0001
    assert por_ruta_etapa[("PLANTA_NORTE→TERMINAL_BAHIA", "EGRESO_DEPOSITO")] == 6000.0
    # C-0008 (ALMACENAMIENTO, sin asignacion) cae en SIN_RUTA
    assert por_ruta_etapa[(SIN_RUTA, "ALMACENAMIENTO")] == 540.0


def test_endpoint_by_route_stage(api, run):
    respuesta = api.get(
        f"/api/v1/simulation-runs/{run.run_id}/cost-explorer/by-route-stage/"
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["importe_considerado"] == CAJA_TOTAL
    assert all({"ruta", "etapa", "importe_usd"} <= set(f) for f in cuerpo["filas"])


def test_endpoint_by_route_reconcilia_contra_el_total(api, run, caja):
    respuesta = api.get(f"/api/v1/simulation-runs/{run.run_id}/cost-explorer/by-route/")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["importe_considerado"] == CAJA_TOTAL
    assert cuerpo["filas_consideradas"] == 8  # 9 cargos totales, 1 ECONOMICO no entra en CAJA


def test_endpoint_by_route_filtra_por_material(api, run):
    respuesta = api.get(
        f"/api/v1/simulation-runs/{run.run_id}/cost-explorer/by-route/?material=MAT_MAP"
    )
    cuerpo = respuesta.json()
    assert cuerpo["filtros_aplicados"]["material"] == "MAT_MAP"
    rutas = {f["ruta"] for f in cuerpo["filas"]}
    assert rutas == {"DEPOSITO_SUR→TERMINAL_BAHIA", SIN_RUTA}


# --- Precio x volumen -------------------------------------------------------------------------


def test_precio_volumen_agrega_cantidad_y_tarifa_promedio_por_categoria(run, caja):
    filas = {f["categoria"]: f for f in costos_por_categoria_con_cantidad(run, caja)}

    out_deposito = filas["OUT_DEPOSITO"]
    # C-0001 (500tn x 12.0) + C-0005 (300tn x 12.0): misma tarifa, cantidad se suma
    assert out_deposito["cantidad"] == 800.0
    assert out_deposito["tarifa_promedio"] == pytest.approx(12.0)
    assert out_deposito["importe_usd"] == 9600.0
    assert out_deposito["unidad"] == "USD_TN"

    flete = filas["FLETE_CONTENEDOR"]
    # C-0002 (20 cont x 1250) + C-0006 (12 cont x 1180): tarifas distintas, promedio ponderado
    assert flete["cantidad"] == 32.0
    assert flete["importe_usd"] == 39160.0
    assert flete["tarifa_promedio"] == pytest.approx(39160.0 / 32.0)


def test_precio_volumen_reconcilia_contra_el_total_de_caja(run, caja):
    filas = costos_por_categoria_con_cantidad(run, caja)
    assert sum(f["importe_usd"] or 0.0 for f in filas) == CAJA_TOTAL


def test_endpoint_price_volume(api, run):
    respuesta = api.get(
        f"/api/v1/simulation-runs/{run.run_id}/cost-explorer/price-volume/"
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["importe_considerado"] == CAJA_TOTAL
    categorias = {f["categoria"] for f in cuerpo["filas"]}
    assert "OUT_DEPOSITO" in categorias
    assert all("tarifa_promedio" in f for f in cuerpo["filas"])
