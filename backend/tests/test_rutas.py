"""Pruebas de ADR-T06 (ruta fisica derivada) y precio x volumen (MOD v6)."""

import pytest
from rest_framework.test import APIClient

from apps.core.models import ArcExecution, AssignmentResult, CostCharge, TipoContable
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


def test_el_costo_sin_asignacion_se_resuelve_por_lote_cuando_no_es_ambiguo(run, caja):
    """ALMACENAMIENTO (C-0008) no tiene id_asignacion, pero su id_lote (L-MAP-01) es el mismo que
    el de A-0002 y ese lote solo alimenta esa ruta: se atribuye ahi, no cae en SIN_RUTA. La suma
    de todas las rutas sigue cerrando contra el total de caja de cualquier manera."""
    filas = costos_por_ruta(run, caja)
    por_ruta = {f["ruta"]: f for f in filas}

    assert SIN_RUTA not in por_ruta
    assert por_ruta["DEPOSITO_SUR→TERMINAL_BAHIA"]["importe_usd"] == pytest.approx(20040.0 + 540.0)

    assert sum(f["importe_usd"] or 0.0 for f in filas) == CAJA_TOTAL


def test_el_costo_por_sitio_se_reparte_por_tonelaje_real_si_el_lote_es_ambiguo(run, caja):
    """Si el mismo lote alimenta dos asignaciones que terminan en rutas distintas, la atribucion
    exacta por lote ya no alcanza. Pero ALMACENAMIENTO trae `sitio` poblado: si ese sitio es una
    parada real de mas de una ruta candidata, el cargo se reparte proporcional al tonelaje real
    de cada una (asignaciones_elegidas) — no en partes iguales, y no se descarta a SIN_RUTA
    solo porque el lote dejo de ser inambiguo. C-0008 (540.0, sitio=DEPOSITO_SUR, ya no
    inambiguo) se reparte con el mismo criterio."""
    ArcExecution.objects.create(
        simulation_run=run,
        id_evento_arco="A-EXTRA-1",
        id_asignacion="A-0002-B",  # otra asignacion, mismo lote, ruta distinta a la de A-0002
        id_lote="L-MAP-01",
        tipo_arco="ORIGEN_TERMINAL_CONTENEDOR_CARGADO",
        origen="DEPOSITO_SUR",
        destino="OTRO_DESTINO",
        dia_inicio=5.0,
        dia_fin=5.5,
    )
    AssignmentResult.objects.create(
        simulation_run=run,
        id_asignacion="A-0002-B",
        toneladas_asignadas=100.0,
    )
    CostCharge.objects.create(
        simulation_run=run,
        id_costo="C-EXTRA-SITIO",
        dia=5.0,
        tipo_contable=TipoContable.CAJA,
        categoria="ALMACENAMIENTO",
        id_lote="L-MAP-01",
        sitio="DEPOSITO_SUR",  # primera parada real de ambas rutas candidatas
        unidad="USD_TN_DIA",
        cantidad=10.0,
        tarifa=40.0,
        importe_usd=400.0,
    )

    filas = {f["ruta"]: f for f in costos_por_ruta(run, caja)}
    tn_terminal, tn_otro = 300.0, 100.0  # toneladas reales de cada ruta candidata
    total_tn = tn_terminal + tn_otro
    reparto_extra = 400.0 * tn_terminal / total_tn
    reparto_c0008 = 540.0 * tn_terminal / total_tn
    assert filas["DEPOSITO_SUR→TERMINAL_BAHIA"]["importe_usd"] == pytest.approx(
        20040.0 + reparto_c0008 + reparto_extra
    )
    reparto_extra_otro = 400.0 * tn_otro / total_tn
    reparto_c0008_otro = 540.0 * tn_otro / total_tn
    assert filas["DEPOSITO_SUR→OTRO_DESTINO"]["importe_usd"] == pytest.approx(
        reparto_c0008_otro + reparto_extra_otro
    )
    assert SIN_RUTA not in filas


def test_el_costo_sin_sitio_reconocible_ni_lote_unico_cae_en_sin_ruta(run, caja):
    """Si ni el `id_lote` resuelve una ruta unica ni el `sitio` del cargo es una parada de
    ninguna ruta reconstruida, no hay base para repartir sin inventar un criterio — se queda en
    SIN_RUTA a proposito, no se descarta."""
    ArcExecution.objects.create(
        simulation_run=run,
        id_evento_arco="A-EXTRA-1",
        id_asignacion="A-0002-B",
        id_lote="L-MAP-01",
        tipo_arco="ORIGEN_TERMINAL_CONTENEDOR_CARGADO",
        origen="DEPOSITO_SUR",
        destino="OTRO_DESTINO",
        dia_inicio=5.0,
        dia_fin=5.5,
    )
    CostCharge.objects.create(
        simulation_run=run,
        id_costo="C-EXTRA-AMBIGUO",
        dia=5.0,
        tipo_contable=TipoContable.CAJA,
        categoria="ALMACENAMIENTO",
        id_lote="L-MAP-01",
        sitio="SITIO_INEXISTENTE",  # no aparece en ninguna ruta reconstruida
        unidad="USD_TN_DIA",
        cantidad=10.0,
        tarifa=1.0,
        importe_usd=10.0,
    )

    filas = {f["ruta"]: f for f in costos_por_ruta(run, caja)}
    assert filas[SIN_RUTA]["importe_usd"] == pytest.approx(10.0)


def test_las_toneladas_por_ruta_salen_de_las_asignaciones(run, caja):
    filas = {f["ruta"]: f for f in costos_por_ruta(run, caja)}

    assert filas["PLANTA_NORTE→TERMINAL_BAHIA"]["toneladas"] == 500.0
    assert filas["DEPOSITO_SUR→TERMINAL_BAHIA"]["toneladas"] == 300.0


def test_el_tramo_planta_deposito_se_antepone_cuando_el_lote_no_es_ambiguo(run, caja):
    """El arco PLANTA_DEPOSITO usa su propio id_asignacion (prefijo TRA-, distinto del ASG- del
    envio final): sin tratarlo aparte, la ruta de A-0001 arrancaria en PLANTA_NORTE y perderia el
    tramo real desde planta. Se une por id_lote (L-UREA-01, compartido con A-0001)."""
    ArcExecution.objects.create(
        simulation_run=run,
        id_evento_arco="A-PLANTA-1",
        id_asignacion="TRA-UREA-1",
        id_lote="L-UREA-01",
        tipo_arco="PLANTA_DEPOSITO",
        origen="PLANTA_CENTRAL",
        destino="PLANTA_NORTE",
        dia_inicio=0.5,
        dia_fin=1.0,
    )

    filas = {f["ruta"]: f for f in costos_por_ruta(run, caja)}

    assert "PLANTA_CENTRAL→PLANTA_NORTE→TERMINAL_BAHIA" in filas
    assert "PLANTA_NORTE→TERMINAL_BAHIA" not in filas
    # el id_asignacion de la transferencia (TRA-...) no aparece como una ruta propia: ningun
    # cargo real lo referencia, solo sirve para encontrar el tramo desde planta
    assert not any(ruta.startswith("TRA-") for ruta in filas)


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
    # C-0008 (ALMACENAMIENTO, sin id_asignacion) se resuelve por id_lote (L-MAP-01, de A-0002)
    assert por_ruta_etapa[("DEPOSITO_SUR→TERMINAL_BAHIA", "ALMACENAMIENTO")] == 540.0


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
    assert rutas == {"DEPOSITO_SUR→TERMINAL_BAHIA"}


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
