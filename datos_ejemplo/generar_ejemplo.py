#!/usr/bin/env python3
"""Genera el paquete de ejemplo `E-00-R0` con el formato que publica AnyLogic (ADR-064.1).

No reemplaza a una corrida real: es un paquete chico, coherente con el esquema publicado, para
poder probar la importacion, el dashboard y la vista "por que" sin depender de una corrida de
AnyLogic. Los encabezados son los mismos que emiten `encabezadoCsv()` y `escribirEsquemaAuditoria()`
del modelo, y por eso se escriben aca literalmente en vez de derivarse de los datos.

Uso:  python datos_ejemplo/generar_ejemplo.py [destino]
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

VERSION_ESQUEMA = "ADR-064.1"
RUN_ID = "E-00-R0"
ESCENARIO = "E-00"
REPLICA = 0
DURACION_CAMPANIA_DIAS = 5

ENCABEZADOS: dict[str, str] = {
    "decisiones_alternativas": (
        "run_id,escenario,replica,dia_simulacion,dia_campania,politica_seleccion,"
        "criterio_orden,id_decision,ronda,id_alternativa,"
        "codigo_pedido,producto,tipo_contenedor,terminal,estado_pedido_antes,"
        "toneladas_solicitadas,toneladas_entregadas_previas,toneladas_en_proceso_previas,"
        "toneladas_reservadas_previas,toneladas_pendientes_asignar,"
        "contenedores_pendientes_estimados,dia_conocimiento,dia_apertura_retiro,dia_cutoff,"
        "dias_hasta_cutoff,cantidad_origenes_previos,"
        "circuito,es_cross_dock,origen_stock,sitio_estiba,destino_final,"
        "requiere_flota_producto,requiere_portacontenedor,requiere_posicion,"
        "tipo_recurso_capacidad,ubicacion_recurso_capacidad,"
        "stock_fisico_origen_tn,stock_libre_origen_tn,stock_reservado_origen_tn,"
        "stock_en_transito_hacia_origen_tn,espacio_fisico_sitio_tn,espacio_efectivo_sitio_tn,"
        "ocupacion_sitio_pct,cupo_crossdock_libre_cont,posiciones_disponibles_antes_cutoff,"
        "flota_producto_disponible,primera_salida_flota,ultima_llegada_flota,"
        "espera_flota_dias,portacontenedores_libres,portacontenedores_ocupados,"
        "toneladas_sin_restriccion_capacidad,toneladas_factibles,contenedores_factibles,"
        "contenedores_con_capacidad,viajes_producto_requeridos,viajes_producto_factibles,"
        "es_asignacion_parcial,porcentaje_pedido_cubierto,"
        "horas_flete_producto,horas_carga_estiba,horas_viaje_vacio,horas_viaje_cargado,"
        "horas_descarga_terminal,horas_consolidacion_terminal,horas_ciclo_fisico_total,"
        "dia_entrega_estimado,holgura_estimada_dias,llega_a_tiempo_estimado,"
        "costo_flete_producto,costo_roundtrip,costo_estiba,costo_out,costo_thc,"
        "costo_terminal,costo_despachante,costo_in_hundido,costo_almacenaje_hundido,"
        "costo_flete_hundido,costo_historico,costo_incremental,costo_end_to_end,"
        "costo_incremental_usd_tn,costo_end_to_end_usd_tn,costo_incremental_usd_cont,"
        "costo_unitario_sin_restriccion,"
        "factible,orden_ranking,resultado_ejecucion,codigo_motivo,detalle_motivo,"
        "toneladas_tomadas,costo_elegida_usd_tn,diferencia_vs_elegida_usd_tn,"
        "saldo_pedido_antes,saldo_pedido_despues,es_mas_barata_no_factible"
    ),
    "asignaciones_elegidas": (
        "run_id,escenario,replica,id_asignacion,id_decision,id_alternativa,"
        "codigo_pedido,producto,origen,circuito,es_cross_dock,prioridad,"
        "dia_asignacion,dia_primer_despacho,dia_ultima_entrega,"
        "toneladas_asignadas,toneladas_reservadas_activas,toneladas_contenerizadas,"
        "toneladas_despachadas,toneladas_entregadas,"
        "contenedores_creados,contenedores_entregados,"
        "costo_incremental_estimado,costo_end_to_end_estimado,"
        "costo_real_contenedores_usd,desvio_costo_usd,"
        "dias_ciclo_real,cerrada,cancelada,motivo_asignacion"
    ),
    "ejecucion_arcos": (
        "run_id,escenario,replica,id_evento_arco,id_decision,id_alternativa,"
        "id_asignacion,id_envio,id_contenedor,codigo_pedido,id_lote,producto,"
        "tipo_arco,origen,destino,circuito,es_cross_dock,"
        "toneladas,contenedores,viajes,distancia_km,"
        "dia_programacion,dia_inicio,dia_fin,duracion_real_horas,duracion_esperada_horas,"
        "recurso_utilizado,id_recurso,estado_final"
    ),
    "costos_eventos": (
        "run_id,escenario,replica,id_costo,dia,dia_campania,tipo_contable,categoria,"
        "codigo_pedido,id_asignacion,id_decision,id_contenedor,id_lote,producto,circuito,"
        "origen,destino,sitio,proveedor,unidad,cantidad,tarifa,importe_usd,id_operacion,"
        "alcance,es_incremental,motivo"
    ),
    "snapshot_inventario": (
        "run_id,escenario,replica,dia,ubicacion,tipo_ubicacion,producto,capacidad_tn,"
        "stock_inicial_dia_tn,stock_fisico_tn,stock_libre_tn,stock_reservado_pedidos_tn,"
        "stock_reservado_viajes_tn,stock_en_transito_entrada_tn,stock_en_transito_salida_tn,"
        "ingresos_dia_tn,egresos_dia_tn,produccion_dia_tn,ocupacion_pct,"
        "costo_almacenaje_dia_usd,dias_stock_promedio,lotes_abiertos,lote_mas_antiguo_dias,"
        "descuadre_tn"
    ),
    "snapshot_capacidad_recursos": (
        "run_id,escenario,replica,dia,tipo_recurso,ubicacion,capacidad_nominal,"
        "reservada,consumida,liberada,ocupada,libre,cola"
    ),
}

ARCHIVOS = {
    "decisiones_alternativas": "decisiones_alternativas.csv",
    "asignaciones_elegidas": "asignaciones_elegidas.csv",
    "ejecucion_arcos": "ejecucion_arcos.csv",
    "costos_eventos": "costos_eventos.csv",
    "snapshot_inventario": "snapshot_inventario.csv",
    "snapshot_capacidad_recursos": "capacidad_por_dia.csv",
}

CLAVES = {
    "decisiones_alternativas": ["run_id", "id_alternativa"],
    "asignaciones_elegidas": ["run_id", "id_asignacion"],
    "ejecucion_arcos": ["run_id", "id_evento_arco"],
    "costos_eventos": ["run_id", "id_costo"],
    "snapshot_inventario": ["run_id", "dia", "ubicacion", "producto"],
    "snapshot_capacidad_recursos": ["run_id", "dia", "tipo_recurso", "ubicacion"],
}


def _fila(tabla: str, valores: dict[str, object]) -> str:
    columnas = ENCABEZADOS[tabla].split(",")
    desconocidas = set(valores) - set(columnas)
    if desconocidas:
        raise ValueError(f"{tabla}: columnas fuera del esquema {sorted(desconocidas)}")
    celdas = []
    for columna in columnas:
        valor = valores.get(columna, "")
        if isinstance(valor, bool):
            valor = "true" if valor else "false"
        celdas.append("" if valor is None else str(valor))
    return ",".join(celdas)


def _decisiones() -> list[str]:
    """Dos pedidos: uno con una alternativa mas barata no factible, otro que se cumple."""
    base = {
        "run_id": RUN_ID,
        "escenario": ESCENARIO,
        "replica": REPLICA,
        "politica_seleccion": "COSTO_INCREMENTAL",
        "criterio_orden": "COSTO_INCREMENTAL_USD_TN",
        "producto": "UREA",
        "tipo_contenedor": "DRY20",
        "terminal": "TERMINAL_BAHIA",
        "estado_pedido_antes": "PENDIENTE",
    }

    filas = [
        # P-0001: la mas barata no es factible por falta de posicion antes del cutoff.
        _fila(
            "decisiones_alternativas",
            base
            | {
                "dia_simulacion": 1.25,
                "dia_campania": 1,
                "id_decision": "P-0001-D1",
                "ronda": 1,
                "id_alternativa": "P-0001-D1-A1",
                "codigo_pedido": "P-0001",
                "toneladas_solicitadas": 500.0,
                "toneladas_pendientes_asignar": 500.0,
                "dia_conocimiento": 0,
                "dia_apertura_retiro": 1,
                "dia_cutoff": 4,
                "dias_hasta_cutoff": 3,
                "circuito": "CIRCUITO_DEPOSITO",
                "es_cross_dock": False,
                "origen_stock": "DEPOSITO_SUR",
                "sitio_estiba": "DEPOSITO_SUR",
                "destino_final": "TERMINAL_BAHIA",
                "requiere_posicion": True,
                "tipo_recurso_capacidad": "POSICION_CONSOLIDACION",
                "ubicacion_recurso_capacidad": "DEPOSITO_SUR",
                "stock_fisico_origen_tn": 900.0,
                "stock_libre_origen_tn": 900.0,
                "posiciones_disponibles_antes_cutoff": 0,
                "toneladas_sin_restriccion_capacidad": 500.0,
                "toneladas_factibles": 0.0,
                "contenedores_factibles": 0,
                "porcentaje_pedido_cubierto": 0.0,
                "costo_incremental": 42000.0,
                "costo_incremental_usd_tn": 84.0,
                "costo_end_to_end_usd_tn": 96.0,
                "factible": False,
                "orden_ranking": 1,
                "resultado_ejecucion": "NO_FACTIBLE",
                "codigo_motivo": "SIN_CAPACIDAD_ANTES_CUTOFF",
                "detalle_motivo": "no quedan posiciones de consolidacion antes del cutoff",
                "toneladas_tomadas": 0.0,
                "costo_elegida_usd_tn": 91.0,
                "diferencia_vs_elegida_usd_tn": -7.0,
                "saldo_pedido_antes": 500.0,
                "saldo_pedido_despues": 500.0,
                "es_mas_barata_no_factible": True,
            },
        ),
        _fila(
            "decisiones_alternativas",
            base
            | {
                "dia_simulacion": 1.25,
                "dia_campania": 1,
                "id_decision": "P-0001-D1",
                "ronda": 1,
                "id_alternativa": "P-0001-D1-A2",
                "codigo_pedido": "P-0001",
                "toneladas_solicitadas": 500.0,
                "toneladas_pendientes_asignar": 500.0,
                "dia_conocimiento": 0,
                "dia_apertura_retiro": 1,
                "dia_cutoff": 4,
                "dias_hasta_cutoff": 3,
                "circuito": "CIRCUITO_PLANTA",
                "es_cross_dock": False,
                "origen_stock": "PLANTA_NORTE",
                "sitio_estiba": "PLANTA_NORTE",
                "destino_final": "TERMINAL_BAHIA",
                "requiere_flota_producto": True,
                "requiere_portacontenedor": True,
                "tipo_recurso_capacidad": "POSICION_CONSOLIDACION",
                "ubicacion_recurso_capacidad": "PLANTA_NORTE",
                "stock_fisico_origen_tn": 1200.0,
                "stock_libre_origen_tn": 1100.0,
                "posiciones_disponibles_antes_cutoff": 6,
                "toneladas_sin_restriccion_capacidad": 500.0,
                "toneladas_factibles": 500.0,
                "contenedores_factibles": 20,
                "contenedores_con_capacidad": 20,
                "porcentaje_pedido_cubierto": 100.0,
                "horas_carga_estiba": 6.0,
                "horas_viaje_cargado": 9.0,
                "horas_descarga_terminal": 3.0,
                "horas_ciclo_fisico_total": 18.0,
                "dia_entrega_estimado": 3,
                "holgura_estimada_dias": 1.0,
                "llega_a_tiempo_estimado": True,
                "costo_incremental": 45500.0,
                "costo_incremental_usd_tn": 91.0,
                "costo_end_to_end_usd_tn": 103.0,
                "factible": True,
                "orden_ranking": 2,
                "resultado_ejecucion": "ELEGIDA",
                "toneladas_tomadas": 500.0,
                "costo_elegida_usd_tn": 91.0,
                "diferencia_vs_elegida_usd_tn": 0.0,
                "saldo_pedido_antes": 500.0,
                "saldo_pedido_despues": 0.0,
                "es_mas_barata_no_factible": False,
            },
        ),
        # P-0002: sin stock en el origen mas barato, se toma el segundo.
        _fila(
            "decisiones_alternativas",
            base
            | {
                "dia_simulacion": 2.10,
                "dia_campania": 2,
                "id_decision": "P-0002-D1",
                "ronda": 1,
                "id_alternativa": "P-0002-D1-A1",
                "codigo_pedido": "P-0002",
                "producto": "MAP",
                "toneladas_solicitadas": 300.0,
                "toneladas_pendientes_asignar": 300.0,
                "dia_conocimiento": 1,
                "dia_apertura_retiro": 2,
                "dia_cutoff": 5,
                "dias_hasta_cutoff": 3,
                "circuito": "CIRCUITO_CROSS_DOCK",
                "es_cross_dock": True,
                "origen_stock": "PLANTA_NORTE",
                "sitio_estiba": "DEPOSITO_SUR",
                "destino_final": "TERMINAL_BAHIA",
                "cupo_crossdock_libre_cont": 0,
                "toneladas_sin_restriccion_capacidad": 300.0,
                "toneladas_factibles": 0.0,
                "porcentaje_pedido_cubierto": 0.0,
                "costo_incremental_usd_tn": 78.0,
                "factible": False,
                "orden_ranking": 1,
                "resultado_ejecucion": "NO_FACTIBLE",
                "codigo_motivo": "SIN_CUPO_CROSS_DOCK",
                "detalle_motivo": "el cupo de cross dock del dia ya estaba tomado",
                "toneladas_tomadas": 0.0,
                "costo_elegida_usd_tn": 88.0,
                "diferencia_vs_elegida_usd_tn": -10.0,
                "saldo_pedido_antes": 300.0,
                "saldo_pedido_despues": 300.0,
                "es_mas_barata_no_factible": True,
            },
        ),
        _fila(
            "decisiones_alternativas",
            base
            | {
                "dia_simulacion": 2.10,
                "dia_campania": 2,
                "id_decision": "P-0002-D1",
                "ronda": 1,
                "id_alternativa": "P-0002-D1-A2",
                "codigo_pedido": "P-0002",
                "producto": "MAP",
                "toneladas_solicitadas": 300.0,
                "toneladas_pendientes_asignar": 300.0,
                "dia_conocimiento": 1,
                "dia_apertura_retiro": 2,
                "dia_cutoff": 5,
                "dias_hasta_cutoff": 3,
                "circuito": "CIRCUITO_DEPOSITO",
                "es_cross_dock": False,
                "origen_stock": "DEPOSITO_SUR",
                "sitio_estiba": "DEPOSITO_SUR",
                "destino_final": "TERMINAL_BAHIA",
                "requiere_portacontenedor": True,
                "stock_fisico_origen_tn": 700.0,
                "stock_libre_origen_tn": 650.0,
                "toneladas_factibles": 300.0,
                "contenedores_factibles": 12,
                "contenedores_con_capacidad": 12,
                "porcentaje_pedido_cubierto": 100.0,
                "horas_carga_estiba": 5.0,
                "horas_viaje_cargado": 7.0,
                "horas_ciclo_fisico_total": 12.0,
                "dia_entrega_estimado": 5,
                "holgura_estimada_dias": 0.0,
                "llega_a_tiempo_estimado": True,
                "costo_incremental_usd_tn": 88.0,
                "costo_end_to_end_usd_tn": 99.0,
                "factible": True,
                "orden_ranking": 2,
                "resultado_ejecucion": "ELEGIDA",
                "toneladas_tomadas": 300.0,
                "costo_elegida_usd_tn": 88.0,
                "diferencia_vs_elegida_usd_tn": 0.0,
                "saldo_pedido_antes": 300.0,
                "saldo_pedido_despues": 0.0,
                "es_mas_barata_no_factible": False,
            },
        ),
        # Alternativa factible que nunca se intento: el pedido ya estaba cubierto.
        _fila(
            "decisiones_alternativas",
            base
            | {
                "dia_simulacion": 2.10,
                "dia_campania": 2,
                "id_decision": "P-0002-D1",
                "ronda": 1,
                "id_alternativa": "P-0002-D1-A3",
                "codigo_pedido": "P-0002",
                "producto": "MAP",
                "toneladas_solicitadas": 300.0,
                "circuito": "CIRCUITO_TERMINAL",
                "origen_stock": "DEPOSITO_SUR",
                "destino_final": "TERMINAL_BAHIA",
                "toneladas_factibles": 300.0,
                "costo_incremental_usd_tn": 105.0,
                "factible": True,
                "orden_ranking": 3,
                "resultado_ejecucion": "NO_INTENTADA",
                "toneladas_tomadas": 0.0,
                "costo_elegida_usd_tn": 88.0,
                "diferencia_vs_elegida_usd_tn": 17.0,
                "saldo_pedido_antes": 0.0,
                "saldo_pedido_despues": 0.0,
                "es_mas_barata_no_factible": False,
            },
        ),
    ]
    return filas


def _asignaciones() -> list[str]:
    base = {"run_id": RUN_ID, "escenario": ESCENARIO, "replica": REPLICA}
    return [
        _fila(
            "asignaciones_elegidas",
            base
            | {
                "id_asignacion": "A-0001",
                "id_decision": "P-0001-D1",
                "id_alternativa": "P-0001-D1-A2",
                "codigo_pedido": "P-0001",
                "producto": "UREA",
                "origen": "PLANTA_NORTE",
                "circuito": "CIRCUITO_PLANTA",
                "es_cross_dock": False,
                "prioridad": 1,
                "dia_asignacion": 1.25,
                "dia_primer_despacho": 1.60,
                "dia_ultima_entrega": 3.40,
                "toneladas_asignadas": 500.0,
                "toneladas_contenerizadas": 500.0,
                "toneladas_despachadas": 500.0,
                "toneladas_entregadas": 500.0,
                "contenedores_creados": 20,
                "contenedores_entregados": 20,
                "costo_incremental_estimado": 45500.0,
                "costo_end_to_end_estimado": 51500.0,
                "costo_real_contenedores_usd": 46850.0,
                "desvio_costo_usd": 1350.0,
                "dias_ciclo_real": 2.15,
                "cerrada": True,
                "cancelada": False,
                "motivo_asignacion": "MEJOR_COSTO_FACTIBLE",
            },
        ),
        _fila(
            "asignaciones_elegidas",
            base
            | {
                "id_asignacion": "A-0002",
                "id_decision": "P-0002-D1",
                "id_alternativa": "P-0002-D1-A2",
                "codigo_pedido": "P-0002",
                "producto": "MAP",
                "origen": "DEPOSITO_SUR",
                "circuito": "CIRCUITO_DEPOSITO",
                "es_cross_dock": False,
                "prioridad": 2,
                "dia_asignacion": 2.10,
                "dia_primer_despacho": 2.80,
                "dia_ultima_entrega": 4.90,
                "toneladas_asignadas": 300.0,
                "toneladas_contenerizadas": 300.0,
                "toneladas_despachadas": 300.0,
                "toneladas_entregadas": 275.0,
                "contenedores_creados": 12,
                "contenedores_entregados": 11,
                "costo_incremental_estimado": 26400.0,
                "costo_end_to_end_estimado": 29700.0,
                "costo_real_contenedores_usd": 27980.0,
                "desvio_costo_usd": 1580.0,
                "dias_ciclo_real": 2.80,
                "cerrada": False,
                "cancelada": False,
                "motivo_asignacion": "MEJOR_COSTO_FACTIBLE",
            },
        ),
    ]


def _arcos() -> list[str]:
    base = {"run_id": RUN_ID, "escenario": ESCENARIO, "replica": REPLICA}
    definiciones = [
        (1, "A-0001", "P-0001-D1", "P-0001-D1-A2", "P-0001", "UREA", "CARGA_CONSOLIDACION",
         "PLANTA_NORTE", "PLANTA_NORTE", 500.0, 20, 1.60, 1.85, 6.0, 6.0, "POSICION"),
        (2, "A-0001", "P-0001-D1", "P-0001-D1-A2", "P-0001", "UREA",
         "ORIGEN_TERMINAL_CONTENEDOR_CARGADO", "PLANTA_NORTE", "TERMINAL_BAHIA", 500.0, 20,
         1.85, 2.25, 9.6, 9.0, "PORTACONTENEDOR"),
        (3, "A-0001", "P-0001-D1", "P-0001-D1-A2", "P-0001", "UREA", "DESCARGA_TERMINAL",
         "TERMINAL_BAHIA", "TERMINAL_BAHIA", 500.0, 20, 2.25, 2.40, 3.6, 3.0, "TERMINAL"),
        (4, "A-0002", "P-0002-D1", "P-0002-D1-A2", "P-0002", "MAP", "ESPERA_PORTACONTENEDOR",
         "DEPOSITO_SUR", "DEPOSITO_SUR", 300.0, 12, 2.30, 2.80, 12.0, -1.0, "PORTACONTENEDOR"),
        (5, "A-0002", "P-0002-D1", "P-0002-D1-A2", "P-0002", "MAP", "CARGA_CONSOLIDACION",
         "DEPOSITO_SUR", "DEPOSITO_SUR", 300.0, 12, 2.80, 3.05, 6.0, 5.0, "POSICION"),
        (6, "A-0002", "P-0002-D1", "P-0002-D1-A2", "P-0002", "MAP",
         "ORIGEN_TERMINAL_CONTENEDOR_CARGADO", "DEPOSITO_SUR", "TERMINAL_BAHIA", 300.0, 12,
         3.05, 3.40, 8.4, 7.0, "PORTACONTENEDOR"),
        (7, "A-0002", "", "", "P-0002", "MAP", "ESPERA_POSICION", "TERMINAL_BAHIA",
         "TERMINAL_BAHIA", 300.0, 12, 3.40, 4.10, 16.8, -1.0, "POSICION"),
    ]
    filas = []
    for (
        numero, asignacion, decision, alternativa, pedido, producto, tipo, origen, destino,
        toneladas, contenedores, inicio, fin, real, esperada, recurso,
    ) in definiciones:
        filas.append(
            _fila(
                "ejecucion_arcos",
                base
                | {
                    "id_evento_arco": numero,
                    "id_decision": decision,
                    "id_alternativa": alternativa,
                    "id_asignacion": asignacion,
                    "id_envio": f"ENV-{numero:04d}",
                    "id_contenedor": f"CNT-{numero:04d}",
                    "codigo_pedido": pedido,
                    "id_lote": f"L-{producto}-01",
                    "producto": producto,
                    "tipo_arco": tipo,
                    "origen": origen,
                    "destino": destino,
                    "circuito": "CIRCUITO_PLANTA" if pedido == "P-0001" else "CIRCUITO_DEPOSITO",
                    "es_cross_dock": False,
                    "toneladas": toneladas,
                    "contenedores": contenedores,
                    "viajes": 1,
                    "distancia_km": 320 if origen != destino else 0,
                    "dia_programacion": inicio,
                    "dia_inicio": inicio,
                    "dia_fin": fin,
                    "duracion_real_horas": real,
                    "duracion_esperada_horas": esperada,
                    "recurso_utilizado": recurso,
                    "id_recurso": f"{recurso}-1",
                    "estado_final": "COMPLETADO",
                },
            )
        )
    return filas


def _costos() -> list[str]:
    base = {"run_id": RUN_ID, "escenario": ESCENARIO, "replica": REPLICA}
    definiciones = [
        ("C-0001", 1.85, 1, "CAJA", "OUT_DEPOSITO", "P-0001", "A-0001", 500.0, 12.0, 6000.0,
         "PEDIDO"),
        ("C-0002", 2.25, 2, "CAJA", "FLETE_CONTENEDOR", "P-0001", "A-0001", 20.0, 1250.0,
         25000.0, "CONTENEDOR"),
        ("C-0003", 2.40, 2, "CAJA", "THC", "P-0001", "A-0001", 20.0, 190.0, 3800.0, "CONTENEDOR"),
        ("C-0004", 2.40, 2, "CAJA", "COSTO_TERMINAL", "P-0001", "A-0001", 20.0, 90.0, 1800.0,
         "CONTENEDOR"),
        ("C-0005", 3.05, 3, "CAJA", "OUT_DEPOSITO", "P-0002", "A-0002", 300.0, 12.0, 3600.0,
         "PEDIDO"),
        ("C-0006", 3.40, 3, "CAJA", "FLETE_CONTENEDOR", "P-0002", "A-0002", 12.0, 1180.0,
         14160.0, "CONTENEDOR"),
        ("C-0007", 4.10, 4, "CAJA", "THC", "P-0002", "A-0002", 12.0, 190.0, 2280.0, "CONTENEDOR"),
        ("C-0008", 4.90, 4, "CAJA", "ALMACENAMIENTO", "", "", 300.0, 1.8, 540.0, "LOTE"),
        # Costo de oportunidad: NO se suma al total de campania (ADR-064 seccion 5.4).
        ("C-0009", 4.90, 4, "ECONOMICO", "OPORTUNIDAD_FRIO", "P-0002", "A-0002", 25.0, 140.0,
         3500.0, "PEDIDO"),
    ]
    filas = []
    for (
        id_costo, dia, dia_campania, tipo_contable, categoria, pedido, asignacion, cantidad,
        tarifa, importe, alcance,
    ) in definiciones:
        sitio = "PLANTA_NORTE" if pedido == "P-0001" else "DEPOSITO_SUR"
        filas.append(
            _fila(
                "costos_eventos",
                base
                | {
                    "id_costo": id_costo,
                    "dia": dia,
                    "dia_campania": dia_campania,
                    "tipo_contable": tipo_contable,
                    "categoria": categoria,
                    "codigo_pedido": pedido,
                    "id_asignacion": asignacion,
                    "id_decision": f"{pedido}-D1" if pedido else "",
                    "id_contenedor": "",
                    "id_lote": "L-UREA-01" if pedido == "P-0001" else "L-MAP-01",
                    "producto": "UREA" if pedido == "P-0001" else "MAP",
                    "circuito": "CIRCUITO_PLANTA" if pedido == "P-0001" else "CIRCUITO_DEPOSITO",
                    "origen": sitio,
                    # El almacenamiento se devenga en el nodo: origen = destino, igual que en el
                    # paquete real, donde los pares mas frecuentes son auto-loops del deposito.
                    "destino": sitio if categoria == "ALMACENAMIENTO" else "TERMINAL_BAHIA",
                    "sitio": sitio,
                    "proveedor": "PROVEEDOR_1",
                    "unidad": (
                        "USD_TN"
                        if categoria in ("OUT_DEPOSITO", "ALMACENAMIENTO", "OPORTUNIDAD_FRIO")
                        else "USD_CONTENEDOR"
                    ),
                    "cantidad": cantidad,
                    "tarifa": tarifa,
                    "importe_usd": importe,
                    "id_operacion": id_costo.replace("C-", "OP-"),
                    "alcance": alcance,
                    "es_incremental": tipo_contable == "CAJA",
                    "motivo": "",
                },
            )
        )
    return filas


def _inventario() -> list[str]:
    base = {"run_id": RUN_ID, "escenario": ESCENARIO, "replica": REPLICA}
    filas = []
    estados = {
        ("PLANTA_NORTE", "UREA"): (1200.0, 2000.0, "PLANTA"),
        ("DEPOSITO_SUR", "MAP"): (700.0, 1500.0, "DEPOSITO"),
    }
    movimientos = {
        ("PLANTA_NORTE", "UREA"): [(0.0, 0.0), (120.0, 0.0), (120.0, 500.0), (120.0, 0.0),
                                   (120.0, 0.0)],
        ("DEPOSITO_SUR", "MAP"): [(0.0, 0.0), (80.0, 0.0), (80.0, 0.0), (80.0, 300.0),
                                  (80.0, 0.0)],
    }
    for (ubicacion, producto), (inicial, capacidad, tipo) in estados.items():
        stock = inicial
        for dia in range(1, DURACION_CAMPANIA_DIAS + 1):
            ingresos, egresos = movimientos[(ubicacion, producto)][dia - 1]
            stock_inicial = stock
            stock = stock_inicial + ingresos - egresos
            filas.append(
                _fila(
                    "snapshot_inventario",
                    base
                    | {
                        "dia": dia,
                        "ubicacion": ubicacion,
                        "tipo_ubicacion": tipo,
                        "producto": producto,
                        "capacidad_tn": capacidad,
                        "stock_inicial_dia_tn": stock_inicial,
                        "stock_fisico_tn": stock,
                        "stock_libre_tn": stock,
                        "stock_reservado_pedidos_tn": 0.0,
                        "stock_reservado_viajes_tn": 0.0,
                        "stock_en_transito_entrada_tn": 0.0,
                        "stock_en_transito_salida_tn": 0.0,
                        "ingresos_dia_tn": ingresos,
                        "egresos_dia_tn": egresos,
                        "produccion_dia_tn": ingresos,
                        "ocupacion_pct": round(100.0 * stock / capacidad, 2),
                        "costo_almacenaje_dia_usd": round(stock * 0.12, 2),
                        "dias_stock_promedio": dia,
                        "lotes_abiertos": 1,
                        "lote_mas_antiguo_dias": dia,
                        "descuadre_tn": 0.0,
                    },
                )
            )
    return filas


def _capacidad() -> list[str]:
    base = {"run_id": RUN_ID, "escenario": ESCENARIO, "replica": REPLICA}
    recursos = [
        ("POSICION_CONSOLIDACION", "PLANTA_NORTE", 8, [2, 6, 5, 3, 1], [0, 0, 0, 0, 0]),
        ("POSICION_CONSOLIDACION", "DEPOSITO_SUR", 6, [1, 3, 6, 6, 2], [0, 0, 2, 1, 0]),
        ("PORTACONTENEDOR", "RED", 10, [3, 7, 9, 8, 4], [0, 1, 3, 2, 0]),
    ]
    filas = []
    for tipo_recurso, ubicacion, nominal, ocupadas, colas in recursos:
        for dia, (ocupada, cola) in enumerate(zip(ocupadas, colas), start=1):
            filas.append(
                _fila(
                    "snapshot_capacidad_recursos",
                    base
                    | {
                        "dia": dia,
                        "tipo_recurso": tipo_recurso,
                        "ubicacion": ubicacion,
                        "capacidad_nominal": nominal,
                        "reservada": max(ocupada - 1, 0),
                        "consumida": ocupada,
                        "liberada": ocupada,
                        "ocupada": ocupada,
                        "libre": nominal - ocupada,
                        "cola": cola,
                    },
                )
            )
    return filas


TABLAS = {
    "decisiones_alternativas": _decisiones,
    "asignaciones_elegidas": _asignaciones,
    "ejecucion_arcos": _arcos,
    "costos_eventos": _costos,
    "snapshot_inventario": _inventario,
    "snapshot_capacidad_recursos": _capacidad,
}

KPIS_BARRIDO = [
    "costo_total_usd",
    "costo_usd_tn",
    "nivel_servicio",
    "atraso_promedio_dias",
    "utilizacion_flota",
    "utilizacion_portacontenedor",
    "toneladas_exportadas",
    "contenedores_exportados",
    "pedidos_sin_alternativa_factible",
    "uso_posiciones_consolidacion",
]

CORRIDAS_BARRIDO = [
    ("E-00", 0, 1001, [57180.0, 73.79, 0.9700, 0.4200, 0.6100, 0.7400, 775.0, 31.0, 0.0, 0.7100]),
    ("E-00", 1, 1002, [57620.0, 74.22, 0.9650, 0.4600, 0.6200, 0.7500, 776.0, 31.0, 0.0, 0.7200]),
    ("E-03", 0, 2001, [61240.0, 71.05, 0.9900, 0.1800, 0.6800, 0.8100, 862.0, 35.0, 0.0, 0.8400]),
    ("E-03", 1, 2002, [61880.0, 71.60, 0.9880, 0.2100, 0.6900, 0.8200, 864.0, 35.0, 0.0, 0.8500]),
]


def escribir(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    filas_por_tabla: dict[str, int] = {}

    for tabla, generar in TABLAS.items():
        filas = generar()
        filas_por_tabla[tabla] = len(filas)
        contenido = "\n".join([ENCABEZADOS[tabla], *filas]) + "\n"
        (destino / ARCHIVOS[tabla]).write_text(contenido, encoding="utf-8")

    esquema = {
        "version_esquema": VERSION_ESQUEMA,
        "tablas": [
            {
                "tabla": tabla,
                "archivo": ARCHIVOS[tabla],
                "clave": CLAVES[tabla],
                "columnas": ENCABEZADOS[tabla].split(","),
            }
            for tabla in TABLAS
        ],
    }
    (destino / "esquema_auditoria.json").write_text(
        json.dumps(esquema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    manifiesto = {
        "run_id": RUN_ID,
        "version_esquema": VERSION_ESQUEMA,
        "escenario": ESCENARIO,
        "replica": REPLICA,
        "nivel_auditoria": "COMPLETA",
        "duracion_campania_dias": DURACION_CAMPANIA_DIAS,
        "generado": "Tue Aug 04 12:00:00 ART 2026",
        "tablas": {
            tabla: {
                "archivo": ARCHIVOS[tabla],
                # capacidad_por_dia se exporta tambien con la auditoria apagada y el modelo
                # informa -1 en vez de un conteo (ADR-064 seccion 5.6).
                "filas": -1 if tabla == "snapshot_capacidad_recursos" else filas_por_tabla[tabla],
            }
            for tabla in TABLAS
        },
        "claves": CLAVES,
    }
    (destino / f"manifiesto_auditoria_{RUN_ID}.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    cabecera = ",".join(["version_modelo", "id_escenario", "replica", "semilla", *KPIS_BARRIDO])
    lineas = [cabecera]
    for escenario, replica, semilla, valores in CORRIDAS_BARRIDO:
        lineas.append(
            ",".join(
                [
                    "2026.08-mvp",
                    escenario,
                    str(replica),
                    str(semilla),
                    *[f"{v:.4f}" for v in valores],
                ]
            )
        )
    (destino.parent / "kpis_por_corrida.csv").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    paquete = destino.parent / f"paquete_auditoria_{RUN_ID}.zip"
    # Solo los archivos del paquete: la carpeta tambien guarda paquetes reales de referencia y
    # meterlos adentro haria que el importador avise de archivos que el esquema no declara.
    del_paquete = {
        *ARCHIVOS.values(),
        "esquema_auditoria.json",
        f"manifiesto_auditoria_{RUN_ID}.json",
    }
    with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in sorted(destino.iterdir()):
            if archivo.name in del_paquete:
                zf.write(archivo, archivo.name)

    return paquete


if __name__ == "__main__":
    raiz = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / RUN_ID
    generado = escribir(raiz)
    print(f"paquete de ejemplo: {generado}")
