"""Pruebas de la agrupacion por dia/semana/mes/anio (MOD v4.1)."""

from datetime import date

import pytest

from apps.dashboard.calendario import AgrupacionInvalida, agrupar_por_periodo, periodo_de


def test_periodo_de_semana_usa_el_lunes():
    etiqueta, referencia = periodo_de(date(2026, 4, 3), "semana")  # viernes

    assert etiqueta == "2026-03-30"  # lunes de esa semana
    assert referencia == date(2026, 3, 30)


def test_periodo_de_mes():
    etiqueta, _ = periodo_de(date(2026, 4, 17), "mes")
    assert etiqueta == "2026-04"


def test_periodo_de_anio():
    etiqueta, _ = periodo_de(date(2026, 12, 30), "anio")
    assert etiqueta == "2026"


def test_agrupar_por_dia_devuelve_una_fila_por_dia():
    filas = [
        {"dia": 1, "fecha": date(2026, 4, 1), "stock_fisico_tn": 100.0},
        {"dia": 2, "fecha": date(2026, 4, 2), "stock_fisico_tn": 120.0},
    ]

    serie = agrupar_por_periodo(
        filas, "dia", campo_fecha="fecha", campo_dia="dia", campos_nivel=("stock_fisico_tn",)
    )

    assert [f["periodo"] for f in serie] == ["2026-04-01", "2026-04-02"]
    assert serie[0]["stock_fisico_tn"] == 100.0
    assert serie[0]["stock_fisico_tn_pico"] == 100.0


def test_agrupar_por_semana_promedia_el_nivel_y_no_lo_suma():
    # Una semana con stock 100 y 120: agrupar no puede dar 220 (eso serian toneladas-dia).
    filas = [
        {"dia": 1, "fecha": date(2026, 3, 30), "stock_fisico_tn": 100.0},  # lunes
        {"dia": 2, "fecha": date(2026, 3, 31), "stock_fisico_tn": 120.0},  # martes, misma semana
        {"dia": 8, "fecha": date(2026, 4, 6), "stock_fisico_tn": 200.0},  # semana siguiente
    ]

    serie = agrupar_por_periodo(
        filas, "semana", campo_fecha="fecha", campo_dia="dia", campos_nivel=("stock_fisico_tn",)
    )

    assert len(serie) == 2
    primera = serie[0]
    assert primera["periodo"] == "2026-03-30"
    assert primera["dias"] == 2
    assert primera["stock_fisico_tn"] == pytest.approx(110.0)  # promedio, no suma
    assert primera["stock_fisico_tn_pico"] == 120.0
    assert primera["fecha_desde"] == "2026-03-30"
    assert primera["fecha_hasta"] == "2026-03-31"


def test_agrupar_por_mes_suma_los_campos_de_flujo():
    filas = [
        {"dia": 1, "fecha": date(2026, 4, 1), "importe_usd": 1000.0},
        {"dia": 2, "fecha": date(2026, 4, 2), "importe_usd": 500.0},
    ]

    serie = agrupar_por_periodo(
        filas, "mes", campo_fecha="fecha", campo_dia="dia", campos_flujo=("importe_usd",)
    )

    assert len(serie) == 1
    assert serie[0]["periodo"] == "2026-04"
    assert serie[0]["importe_usd"] == 1500.0


def test_agrupar_ordena_los_periodos_cronologicamente_no_alfabeticamente():
    # "2026-09" es alfabeticamente menor que "2026-12" por casualidad, pero probamos el borde de
    # anio real: diciembre de 2026 antes que enero de 2027.
    filas = [
        {"dia": 1, "fecha": date(2027, 1, 5), "stock_fisico_tn": 10.0},
        {"dia": 0, "fecha": date(2026, 12, 20), "stock_fisico_tn": 20.0},
    ]

    serie = agrupar_por_periodo(
        filas, "mes", campo_fecha="fecha", campo_dia="dia", campos_nivel=("stock_fisico_tn",)
    )

    assert [f["periodo"] for f in serie] == ["2026-12", "2027-01"]


def test_filas_sin_fecha_se_declaran_en_vez_de_perderse():
    filas = [
        {"dia": 1, "fecha": date(2026, 4, 1), "stock_fisico_tn": 100.0},
        {"dia": 2, "fecha": None, "stock_fisico_tn": 50.0},
    ]

    serie = agrupar_por_periodo(
        filas, "mes", campo_fecha="fecha", campo_dia="dia", campos_nivel=("stock_fisico_tn",)
    )

    periodos = {f["periodo"] for f in serie}
    assert "SIN_FECHA" in periodos
    sin_fecha = next(f for f in serie if f["periodo"] == "SIN_FECHA")
    assert sin_fecha["dias"] == 1


def test_agrupacion_desconocida_se_rechaza():
    with pytest.raises(AgrupacionInvalida):
        agrupar_por_periodo([], "trimestre", campo_fecha="fecha", campo_dia="dia")
