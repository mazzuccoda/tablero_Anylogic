"""Endpoints del Cost Explorer.

PR-01 expone el resumen, los desgloses por etapa y por categoria, y la reconciliacion. Los demas
niveles (producto, circuito, ubicacion, arco, pedido, decision, eventos) llegan en los PR siguientes
sobre estos mismos filtros y agregados.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.models import SimulationRun, TipoCorrida

from . import agregados, reconciliacion
from .filtros import FiltroInvalido, FiltrosCostos


def _run(identificador: str) -> SimulationRun:
    if str(identificador).isdigit():
        return get_object_or_404(SimulationRun, pk=int(identificador))
    return get_object_or_404(SimulationRun, run_id=identificador)


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


@api_view(["GET"])
def por_etapa(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    filas = agregados.costos_por_etapa(run, filtros)
    return Response(
        {
            "run_id": run.run_id,
            "tipo_contable": filtros.tipo_contable,
            "filtros_aplicados": filtros.como_dict(),
            "importe_considerado": sum(fila["importe_usd"] or 0.0 for fila in filas),
            "filas": filas,
        }
    )


@api_view(["GET"])
def por_categoria(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    if error:
        return error
    filas = agregados.costos_por_categoria(run, filtros)
    return Response(
        {
            "run_id": run.run_id,
            "tipo_contable": filtros.tipo_contable,
            "filtros_aplicados": filtros.como_dict(),
            "importe_considerado": sum(fila["importe_usd"] or 0.0 for fila in filas),
            "filas": filas,
        }
    )


@api_view(["GET"])
def reconciliar(request, identificador):
    run, filtros, error = _preparar(request, identificador)
    return error or Response(reconciliacion.reconciliar_costos(run, filtros))
