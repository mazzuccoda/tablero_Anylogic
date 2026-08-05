"""Pruebas del Cost Explorer (MOD v3.2, PR-01)."""

import pytest
from rest_framework.test import APIClient

from apps.core.models import ArcExecution, CostCharge, TipoContable
from apps.dashboard.cost_explorer import (
    ETAPA_NO_CLASIFICADA,
    ETAPA_POR_CATEGORIA,
    FiltrosCostos,
    clasificar_etapa,
    costos_por_etapa,
    reconciliar_costos,
    resumen_costos,
    tipo_geografia,
    toneladas_por_contenedor,
    toneladas_por_lote,
)
from apps.dashboard.cost_explorer.objetos import costo_por_objeto
from apps.dashboard.cost_explorer.reconciliacion import (
    DESCUADRADA,
    EXACTA,
    PARCIAL,
    categorias_sin_clasificar,
)
from apps.ingest.importadores import importar_kpis_barrido, importar_paquete_auditoria

pytestmark = pytest.mark.django_db

CAJA_TOTAL = 57180.0
TN_ENTREGADAS = 775.0
ALMACENAMIENTO_SIN_PEDIDO = 540.0


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def run(paquete):
    return importar_paquete_auditoria(paquete).simulation_run


@pytest.fixture
def caja() -> FiltrosCostos:
    return FiltrosCostos()


def test_la_etapa_sale_de_la_categoria_del_contrato():
    assert clasificar_etapa("ALMACENAMIENTO") == "ALMACENAMIENTO"
    assert clasificar_etapa("FLETE_PRODUCTO") == "TRANSFERENCIA_PLANTA_DEPOSITO"
    assert clasificar_etapa("ROUND_TRIP") == "RETIRO_CONTENEDOR"
    assert clasificar_etapa("COSTO_TERMINAL") == "TERMINAL"
    assert clasificar_etapa("OPORTUNIDAD_FRIO") == "OPORTUNIDAD"


def test_una_categoria_desconocida_no_cae_en_un_cajon_de_sastre():
    """Si el modelo escribe un costo nuevo hay que enterarse, no absorberlo en "OTROS"."""
    assert clasificar_etapa("CANON_PORTUARIO_2027") == ETAPA_NO_CLASIFICADA


def test_el_respaldo_por_alcance_y_geografia_solo_corre_sin_categoria():
    assert clasificar_etapa("", alcance="CONTENEDOR") == "TRANSPORTE_CONTENEDOR"
    assert clasificar_etapa("", origen="NORRY", destino="NORRY") == "ALMACENAMIENTO"
    assert clasificar_etapa("", origen="PLANTA", destino="T4") == "TRANSFERENCIA_PLANTA_DEPOSITO"
    assert clasificar_etapa("", origen="PLANTA", destino="") == ETAPA_NO_CLASIFICADA


def test_el_costo_de_nodo_no_es_un_arco():
    """En el paquete real los pares mas frecuentes son auto-loops del deposito."""
    assert tipo_geografia("RUTA9", "RUTA9") == "NODO"
    assert tipo_geografia("PLANTA", "T4") == "ARCO"
    assert tipo_geografia("", "T4") == "GEOGRAFIA_NO_CLASIFICADA"


def test_el_paquete_de_ejemplo_no_tiene_categorias_sin_clasificar(run, caja):
    """Contrato vivo: una categoria nueva en el paquete rompe esta prueba."""
    assert categorias_sin_clasificar(run, caja) == []
    assert set(CostCharge.objects.values_list("categoria", flat=True)) <= set(ETAPA_POR_CATEGORIA)


def test_el_resumen_no_mezcla_caja_con_economico(run, caja):
    datos = resumen_costos(run, caja)

    assert datos["tipo_contable"] == TipoContable.CAJA
    assert datos["importe_usd"] == pytest.approx(CAJA_TOTAL)
    assert datos["contraparte"]["tipo_contable"] == TipoContable.ECONOMICO
    assert datos["contraparte"]["importe_usd"] == pytest.approx(3500.0)


def test_cada_ratio_del_resumen_declara_su_base(run, caja):
    datos = resumen_costos(run, caja)

    assert datos["usd_por_tn"]["base"] == {"nombre": "tn_entregadas", "valor": TN_ENTREGADAS}
    assert datos["usd_por_tn"]["valor"] == pytest.approx(CAJA_TOTAL / TN_ENTREGADAS)
    assert datos["usd_por_contenedor"]["base"]["nombre"] == "contenedores_entregados"
    assert datos["usd_por_pedido"]["base"] == {"nombre": "pedidos_con_entrega", "valor": 2}


def test_el_usd_tn_no_se_calcula_sobre_la_suma_de_cantidad(run, caja):
    """`cantidad` mezcla USD_TN con USD_CONTENEDOR: sumarla no da toneladas."""
    cantidades = sum(
        c.cantidad for c in CostCharge.objects.filter(tipo_contable=TipoContable.CAJA)
    )

    datos = resumen_costos(run, caja)

    assert cantidades != pytest.approx(TN_ENTREGADAS)
    assert datos["usd_por_tn"]["valor"] != pytest.approx(CAJA_TOTAL / cantidades)


def test_el_desglose_por_etapa_suma_el_total_y_va_en_orden_logistico(run, caja):
    filas = costos_por_etapa(run, caja)

    assert sum(fila["importe_usd"] for fila in filas) == pytest.approx(CAJA_TOTAL)
    assert [fila["etapa"] for fila in filas] == [
        "ALMACENAMIENTO",
        "EGRESO_DEPOSITO",
        "TRANSPORTE_CONTENEDOR",
        "TERMINAL",
        "THC",
    ]
    almacenamiento = next(f for f in filas if f["etapa"] == "ALMACENAMIENTO")
    assert almacenamiento["importe_usd"] == pytest.approx(ALMACENAMIENTO_SIN_PEDIDO)
    assert almacenamiento["categorias"] == ["ALMACENAMIENTO"]
    assert almacenamiento["porcentaje"] == pytest.approx(
        ALMACENAMIENTO_SIN_PEDIDO / CAJA_TOTAL * 100
    )


def test_la_reconciliacion_es_exacta_en_las_dimensiones_que_el_contrato_siempre_escribe(run, caja):
    datos = reconciliar_costos(run, caja)

    assert datos["total_usd"] == pytest.approx(CAJA_TOTAL)
    assert datos["dimensiones_descuadradas"] == []
    for dimension in ("etapa", "categoria", "producto", "circuito", "origen", "destino", "sitio"):
        assert datos["dimensiones"][dimension]["estado"] == EXACTA, dimension
        assert datos["dimensiones"][dimension]["diferencia"] == pytest.approx(0.0), dimension


def test_la_reconciliacion_declara_parcial_el_desglose_por_pedido(run, caja):
    """El almacenamiento se devenga por lote: el desglose por pedido no puede reconciliar."""
    pedido = reconciliar_costos(run, caja)["dimensiones"]["codigo_pedido"]

    assert pedido["estado"] == PARCIAL
    assert pedido["suma"] == pytest.approx(CAJA_TOTAL - ALMACENAMIENTO_SIN_PEDIDO)
    assert pedido["diferencia"] == pytest.approx(ALMACENAMIENTO_SIN_PEDIDO)
    assert "no trae pedido" in pedido["motivo"]


def test_un_cargo_de_una_categoria_nueva_aparece_en_la_reconciliacion(run, caja):
    CostCharge.objects.create(
        simulation_run=run,
        id_costo="C-9999",
        dia=5.0,
        tipo_contable=TipoContable.CAJA,
        categoria="CANON_PORTUARIO_2027",
        producto="UREA",
        circuito="CIRCUITO_PLANTA",
        origen="PLANTA_NORTE",
        destino="TERMINAL_BAHIA",
        sitio="PLANTA_NORTE",
        alcance="PEDIDO",
        unidad="USD_TN",
        cantidad=10.0,
        importe_usd=1000.0,
    )

    datos = reconciliar_costos(run, caja)

    assert datos["etapa_no_clasificada_usd"] == pytest.approx(1000.0)
    assert datos["categorias_sin_clasificar"][0]["categoria"] == "CANON_PORTUARIO_2027"
    # La plata sin clasificar sigue dentro del total: el desglose por etapa no la pierde.
    assert datos["dimensiones"]["etapa"]["estado"] == EXACTA
    assert datos["dimensiones"]["etapa"]["diferencia"] == pytest.approx(0.0)
    assert DESCUADRADA not in {fila["estado"] for fila in datos["dimensiones"].values()}


def test_toneladas_por_lote_prefiere_el_arco_y_usa_el_cargo_como_respaldo(run):
    ArcExecution.objects.create(
        simulation_run=run,
        id_evento_arco="A-IN-1",
        id_lote="L-UREA-01",
        tipo_arco="PLANTA_DEPOSITO",
        toneladas=500.0,
    )
    CostCharge.objects.create(
        simulation_run=run,
        id_costo="C-IN-1",
        dia=1.0,
        tipo_contable=TipoContable.CAJA,
        categoria="IN_DEPOSITO",
        id_lote="L-UREA-01",
        unidad="USD_TN",
        cantidad=999.0,
        tarifa=2.5,
        importe_usd=2497.5,
    )
    CostCharge.objects.create(
        simulation_run=run,
        id_costo="C-IN-2",
        dia=1.0,
        tipo_contable=TipoContable.CAJA,
        categoria="IN_DEPOSITO",
        id_lote="L-MAP-01",
        unidad="USD_TN",
        cantidad=300.0,
        tarifa=2.5,
        importe_usd=750.0,
    )

    toneladas = toneladas_por_lote(run)

    assert toneladas["L-UREA-01"] == pytest.approx(500.0)
    assert toneladas["L-MAP-01"] == pytest.approx(300.0)


def test_el_usd_tn_del_lote_usa_las_toneladas_del_lote_no_las_toneladas_dia(run, caja):
    """El almacenamiento viene en USD_TN_DIA: su `cantidad` acumulada no son toneladas."""
    ArcExecution.objects.create(
        simulation_run=run,
        id_evento_arco="A-IN-2",
        id_lote="L-FRIO-01",
        tipo_arco="PLANTA_DEPOSITO",
        toneladas=100.0,
    )
    for dia in range(1, 11):
        CostCharge.objects.create(
            simulation_run=run,
            id_costo=f"C-ALM-{dia}",
            dia=float(dia),
            tipo_contable=TipoContable.CAJA,
            categoria="ALMACENAMIENTO",
            id_lote="L-FRIO-01",
            unidad="USD_TN_DIA",
            cantidad=100.0,
            tarifa=0.48,
            importe_usd=48.0,
        )

    fila = next(f for f in costo_por_objeto(run, caja, "id_lote") if f["id_lote"] == "L-FRIO-01")

    assert fila["importe_usd"] == pytest.approx(480.0)
    assert fila["toneladas"] == pytest.approx(100.0)
    assert fila["usd_por_tn"] == pytest.approx(4.8)


def test_toneladas_por_contenedor_salen_del_arco_de_carga(run):
    toneladas = toneladas_por_contenedor(run)

    assert toneladas["CNT-0001"] == pytest.approx(500.0)
    assert toneladas["CNT-0005"] == pytest.approx(300.0)


def test_los_filtros_recortan_por_etapa_sin_columna_derivada(run):
    filtros = FiltrosCostos(etapa="ALMACENAMIENTO")

    datos = resumen_costos(run, filtros)

    assert datos["importe_usd"] == pytest.approx(ALMACENAMIENTO_SIN_PEDIDO)
    assert datos["filtros_aplicados"] == {"tipo_contable": "CAJA", "etapa": "ALMACENAMIENTO"}


def test_el_recorte_por_dia_no_arrastra_cargos_de_otros_dias(run):
    datos = resumen_costos(run, FiltrosCostos(dia_desde=3.0, dia_hasta=4.9))

    assert datos["importe_usd"] == pytest.approx(3600.0 + 14160.0 + 2280.0 + 540.0)
    assert datos["filas_consideradas"] == 4


def test_la_api_devuelve_el_resumen_con_la_firma_del_recorte(api, run):
    respuesta = api.get(
        "/api/v1/simulation-runs/E-00-R0/cost-explorer/summary/", {"producto": "UREA"}
    )
    datos = respuesta.json()

    assert respuesta.status_code == 200
    assert datos["importe_usd"] == pytest.approx(6000.0 + 25000.0 + 3800.0 + 1800.0)
    assert datos["filtros_aplicados"] == {"tipo_contable": "CAJA", "producto": "UREA"}
    assert datos["filas_consideradas"] == 4


def test_la_api_rechaza_un_filtro_que_no_esta_en_la_lista_blanca(api, run):
    respuesta = api.get(
        "/api/v1/simulation-runs/E-00-R0/cost-explorer/summary/", {"importe_usd__gt": "0"}
    )

    assert respuesta.status_code == 400
    assert "filtro desconocido" in respuesta.json()["detalle"]


def test_la_api_rechaza_un_rango_de_dias_invertido(api, run):
    respuesta = api.get(
        "/api/v1/simulation-runs/E-00-R0/cost-explorer/summary/",
        {"dia_desde": "9", "dia_hasta": "2"},
    )

    assert respuesta.status_code == 400
    assert "dia_desde" in respuesta.json()["detalle"]


def test_la_api_rechaza_un_tipo_contable_inventado(api, run):
    respuesta = api.get(
        "/api/v1/simulation-runs/E-00-R0/cost-explorer/summary/", {"tipo_contable": "TOTAL"}
    )

    assert respuesta.status_code == 400


def test_la_api_expone_la_reconciliacion_y_el_desglose_por_etapa(api, run):
    etapas = api.get("/api/v1/simulation-runs/E-00-R0/cost-explorer/by-stage/").json()
    reconciliacion = api.get(
        "/api/v1/simulation-runs/E-00-R0/cost-explorer/reconciliation/"
    ).json()

    assert etapas["importe_considerado"] == pytest.approx(CAJA_TOTAL)
    assert reconciliacion["dimensiones"]["producto"]["estado"] == EXACTA
    assert reconciliacion["dimensiones"]["codigo_pedido"]["estado"] == PARCIAL


def test_una_corrida_de_barrido_no_tiene_cost_explorer(api, kpis_barrido):
    importar_kpis_barrido(kpis_barrido)

    respuesta = api.get("/api/v1/simulation-runs/E-03-R0/cost-explorer/summary/")

    assert respuesta.status_code == 409
    assert "barrido" in respuesta.json()["detalle"]
    assert respuesta.json()["tiene_drill_down"] is False
