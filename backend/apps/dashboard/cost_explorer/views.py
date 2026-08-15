"""Endpoints del Cost Explorer.

Todos comparten el mismo recorte (`FiltrosCostos`) y devuelven `filtros_aplicados`, asi que un
numero de la pantalla se puede reproducir con la URL. Los desgloses por objeto de costo (lote,
contenedor, pedido) traen ademas su USD/tn con la base fisica que uso, y el sobrecosto por
restriccion viaja aparte porque es un contrafactual y no un cargo.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.models import SimulationRun, TipoCorrida
from apps.dashboard import almacenamiento

from . import agregados, dimensiones, flujo_fisico, objetos, reconciliacion, restricciones, rutas
from . import eventos as modulo_eventos
from .dimensiones import DimensionInvalida
from .eventos import PaginacionInvalida
from .filtros import FiltroInvalido, FiltrosCostos


def _run(identificador: str) -> SimulationRun:
    if str(identificador).isdigit():
        return get_object_or_404(SimulationRun, pk=int(identificador))
    return get_object_or_404(SimulationRun, run_id=identificador)


def _ubicaciones(run: SimulationRun) -> list[str]:
    return sorted(fila["ubicacion"] for fila in almacenamiento.depositos(run))


def _preparar(request, identificador: str):
    """Resuelve corrida y filtros, o devuelve la respuesta de error que corresponda.

    Una corrida de barrido no tiene `costos_eventos`: contesta 409 con el motivo, igual que la vista
    por pedido. Devolver paneles en cero seria peor que no tener la pantalla.
    """
    run = _run(identificador)
    if run.tipo != TipoCorrida.AUDITORIA:
        return None, None, Response(
            {
                "detalle": (
                    f"la corrida {run.run_id} es de barrido (nivelAuditoriaRed = DESACTIVADA) y no "
                    "trae costos_eventos: el Cost Explorer necesita una corrida auditada"
                ),
                "tiene_drill_down": False,
            },
            status=409,
        )

    try:
        filtros = FiltrosCostos.desde_query_params(request.query_params)
    except FiltroInvalido as exc:
        return None, None, Response({"detalle": str(exc)}, status=400)

    return run, filtros, None


@api_view(["GET"])
def resumen(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    return error or Response(agregados.resumen_costos(run, filtros))


def _respuesta_de_filas(run, filtros, filas: list[dict], extra: dict | None = None) -> Response:
    """Envoltorio comun de los desgloses.

    Siempre viaja `filas_consideradas` junto a `importe_considerado`: un desglose vacio por filtro
    tiene que distinguirse de un desglose vacio por falta de datos.
    """
    cuerpo = {
        "run_id": run.run_id,
        "tipo_contable": filtros.tipo_contable,
        "filtros_aplicados": filtros.como_dict(),
        "filas_consideradas": sum(fila.get("eventos") or 0 for fila in filas),
        "importe_considerado": sum(fila["importe_usd"] or 0.0 for fila in filas) if filas else None,
        "filas": filas,
    }
    cuerpo.update(extra or {})
    return Response(cuerpo)


@api_view(["GET"])
def por_etapa(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    return _respuesta_de_filas(run, filtros, agregados.costos_por_etapa(run, filtros))


@api_view(["GET"])
def por_ruta(request, identificador):
    """ADR-T06 (MOD v6): costo y toneladas por ruta fisica derivada (secuencia de sitios de
    `ejecucion_arcos`), no por el `circuito` declarado (que es un tipo de consolidacion, no una
    ruta con nombre)."""
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    return _respuesta_de_filas(run, filtros, rutas.costos_por_ruta(run, filtros))


@api_view(["GET"])
def por_ruta_y_etapa(request, identificador):
    """ADR-T06 (MOD v6): cruce etapa x ruta para la matriz "estrategia por producto"."""
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    return _respuesta_de_filas(run, filtros, rutas.costos_por_ruta_y_etapa(run, filtros))


@api_view(["GET"])
def por_categoria(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    return _respuesta_de_filas(run, filtros, agregados.costos_por_categoria(run, filtros))


@api_view(["GET"])
def precio_volumen(request, identificador):
    """MOD v6: cantidad y tarifa promedio por categoria, para descomponer un cambio de importe
    entre dos corridas en efecto precio y efecto volumen (la resta se hace en el cliente,
    comparando dos llamadas a este mismo endpoint)."""
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    return _respuesta_de_filas(
        run, filtros, agregados.costos_por_categoria_con_cantidad(run, filtros)
    )


@api_view(["GET"])
def por_dimension(request, identificador, dimension):
    """Desglose por una columna de `costos_eventos` de la lista blanca."""
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    try:
        filas = dimensiones.costos_por_dimension(run, filtros, dimension)
    except DimensionInvalida as exc:
        return Response({"detalle": str(exc)}, status=400)
    return _respuesta_de_filas(run, filtros, filas, {"dimension": dimension})


@api_view(["GET"])
def por_arco(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    filas = dimensiones.costos_por_arco(run, filtros)
    return _respuesta_de_filas(run, filtros, filas, dimensiones.resumen_nodo_arco(filas))


@api_view(["GET"])
def por_objeto(request, identificador, objeto):
    """Costo y USD/tn por lote, contenedor o pedido, con las toneladas fisicas del objeto."""
    clave = objetos.CLAVE_POR_OBJETO.get(objeto)
    if clave is None:
        return Response(
            {
                "detalle": (
                    f"objeto de costo desconocido {objeto!r}; opciones: "
                    f"{', '.join(sorted(objetos.CLAVE_POR_OBJETO))}"
                )
            },
            status=400,
        )

    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    filas = objetos.costo_por_objeto(run, filtros, clave)
    return _respuesta_de_filas(
        run,
        filtros,
        filas,
        {
            "objeto": objeto,
            "clave": clave,
            "base": objetos.BASE_POR_CLAVE[clave],
            "objetos_sin_toneladas": sum(1 for fila in filas if fila["toneladas"] is None),
        },
    )


@api_view(["GET"])
def waterfall(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    return error or Response(dimensiones.waterfall(run, filtros))


@api_view(["GET"])
def eventos(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    try:
        return Response(modulo_eventos.eventos(run, filtros, request.query_params))
    except PaginacionInvalida as exc:
        return Response({"detalle": str(exc)}, status=400)


@api_view(["GET"])
def sobrecosto_por_restriccion(request, identificador):
    """Contrafactual del modelo: no lleva filtros de `costos_eventos` porque no suma cargos."""
    run, _filtros, error = _preparar(request, identificador)
    return error or Response(restricciones.sobrecosto_por_restriccion(run))


@api_view(["GET"])
def reconciliar(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    return error or Response(reconciliacion.reconciliar_costos(run, filtros))


@api_view(["GET"])
def cintas(request, identificador):
    """Flujo fisico por etapa: toneladas de los arcos y costo de costos_eventos, sin almacenaje."""
    run, filtros, error = _preparar(request, identificador)
    return error or Response(flujo_fisico.cintas_por_etapa(run, filtros))


@api_view(["GET"])
def almacenaje_por_producto(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    return error or Response(almacenamiento.por_producto(run, filtros))


@api_view(["GET"])
def almacenaje_depositos(request, identificador):
    run, _filtros, error = _preparar(request, identificador)
    return error or Response({"run_id": run.run_id, "depositos": almacenamiento.depositos(run)})


@api_view(["GET"])
def deposito_flujo_y_decision(request, identificador, ubicacion):
    """Flujo, costo y motivo de decision de un deposito, en la misma respuesta y sin aplanarlos."""
    run, _filtros, error = _preparar(request, identificador)
    if error:
        return error
    if ubicacion not in _ubicaciones(run):
        return Response(
            {
                "detalle": (
                    f"la corrida {run.run_id} no tiene inventario en {ubicacion!r}; "
                    f"sitios con stock: {', '.join(_ubicaciones(run))}"
                )
            },
            status=404,
        )
    return Response(almacenamiento.flujo_y_decision(run, ubicacion))


@api_view(["GET"])
def deposito_stock_diario(request, identificador, ubicacion):
    run, _filtros, error = _preparar(request, identificador)
    if error:
        return error
    datos = almacenamiento.serie_diaria(run, ubicacion)
    if not datos["serie_diaria"]:
        return Response(
            {"detalle": f"la corrida {run.run_id} no tiene inventario en {ubicacion!r}"}, status=404
        )
    return Response(datos)


@api_view(["GET"])
def top_lotes(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    try:
        return Response(
            almacenamiento.top_lotes(run, filtros, request.query_params.get("orden", "costo"))
        )
    except almacenamiento.OrdenInvalido as exc:
        return Response({"detalle": str(exc)}, status=400)


@api_view(["GET"])
def recorrido_de_lote(request, identificador, id_lote):
    """Recorrido fisico de un lote y su costo de almacenaje."""
    run, _filtros, error = _preparar(request, identificador)
    if error:
        return error
    datos = almacenamiento.recorrido_de_lote(run, id_lote)
    if not datos["recorrido"] and datos["costo_almacenaje_usd"] is None:
        return Response(
            {"detalle": f"la corrida {run.run_id} no tiene arcos ni cargos del lote {id_lote!r}"},
            status=404,
        )
    return Response(datos)
