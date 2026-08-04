import csv

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.models import (
    ArcExecution,
    AssignmentResult,
    CostCharge,
    DecisionAlternative,
    InventorySnapshot,
    ResourceCapacitySnapshot,
    ScenarioRunKpi,
    SimulationRun,
)
from apps.core.serializers import (
    ArcExecutionSerializer,
    AssignmentResultSerializer,
    CostChargeSerializer,
    DecisionAlternativeSerializer,
    InventorySnapshotSerializer,
    ResourceCapacitySnapshotSerializer,
    ScenarioRunKpiSerializer,
)

from . import agregados

TABLAS_EXPORTABLES = {
    "decisiones": (DecisionAlternative, DecisionAlternativeSerializer),
    "asignaciones": (AssignmentResult, AssignmentResultSerializer),
    "arcos": (ArcExecution, ArcExecutionSerializer),
    "costos": (CostCharge, CostChargeSerializer),
    "inventario": (InventorySnapshot, InventorySnapshotSerializer),
    "capacidad": (ResourceCapacitySnapshot, ResourceCapacitySnapshotSerializer),
}


def _run(identificador: str) -> SimulationRun:
    if str(identificador).isdigit():
        return get_object_or_404(SimulationRun, pk=int(identificador))
    return get_object_or_404(SimulationRun, run_id=identificador)


@api_view(["GET"])
def dashboard_corrida(request, identificador):
    return Response(agregados.dashboard(_run(identificador)))


@api_view(["GET"])
def inventario_corrida(request, identificador):
    run = _run(identificador)
    filas = InventorySnapshot.objects.filter(simulation_run=run).order_by(
        "dia", "ubicacion", "producto"
    )
    ubicacion = request.query_params.get("ubicacion")
    if ubicacion:
        filas = filas.filter(ubicacion=ubicacion)
    return Response(
        {
            "resumen": agregados.inventario(run),
            "filas": InventorySnapshotSerializer(filas, many=True).data,
        }
    )


@api_view(["GET"])
def costos_corrida(request, identificador):
    run = _run(identificador)
    filas = CostCharge.objects.filter(simulation_run=run).order_by("dia")
    tipo_contable = request.query_params.get("tipo_contable")
    if tipo_contable:
        filas = filas.filter(tipo_contable=tipo_contable)
    categoria = request.query_params.get("categoria")
    if categoria:
        filas = filas.filter(categoria=categoria)
    return Response(
        {
            "resumen": agregados.costos(run),
            "filas": CostChargeSerializer(filas[:5000], many=True).data,
        }
    )


@api_view(["GET"])
def capacidad_corrida(request, identificador):
    run = _run(identificador)
    filas = ResourceCapacitySnapshot.objects.filter(simulation_run=run).order_by(
        "dia", "tipo_recurso", "ubicacion"
    )
    return Response(
        {
            "resumen": agregados.capacidad(run),
            "filas": ResourceCapacitySnapshotSerializer(filas, many=True).data,
        }
    )


@api_view(["GET"])
def decisiones_corrida(request, identificador):
    run = _run(identificador)
    filas = DecisionAlternative.objects.filter(simulation_run=run).order_by(
        "codigo_pedido", "ronda", "orden_ranking"
    )
    for campo in ("codigo_pedido", "codigo_motivo", "resultado_ejecucion"):
        valor = request.query_params.get(campo)
        if valor:
            filas = filas.filter(**{campo: valor})
    if request.query_params.get("solo_mas_baratas_no_factibles") == "1":
        filas = filas.filter(es_mas_barata_no_factible=True)
    return Response(DecisionAlternativeSerializer(filas[:5000], many=True).data)


@api_view(["GET"])
def por_que_pedido(request, codigo_pedido):
    """CU-04. `run_id` es obligatorio: el drill-down es siempre de una corrida."""
    run_id = request.query_params.get("run_id")
    if not run_id:
        return Response({"detalle": "falta el parametro run_id"}, status=400)

    run = _run(run_id)
    if not run.tiene_drill_down:
        return Response(
            {
                "detalle": (
                    f"la corrida {run.run_id} es de barrido (nivelAuditoriaRed = DESACTIVADA) y no "
                    "tiene tablas de auditoria: no hay vista por pedido para esta corrida"
                ),
                "tiene_drill_down": False,
            },
            status=409,
        )

    datos = agregados.por_que(run, codigo_pedido)
    if not datos["decisiones"].exists() and not datos["asignaciones"].exists():
        raise Http404(f"no hay datos del pedido {codigo_pedido} en la corrida {run.run_id}")

    return Response(
        {
            "run_id": datos["run_id"],
            "codigo_pedido": datos["codigo_pedido"],
            "resumen": datos["resumen"],
            "decisiones": DecisionAlternativeSerializer(datos["decisiones"], many=True).data,
            "asignaciones": AssignmentResultSerializer(datos["asignaciones"], many=True).data,
            "arcos": ArcExecutionSerializer(datos["arcos"], many=True).data,
            "cargos": CostChargeSerializer(datos["cargos"], many=True).data,
        }
    )


@api_view(["GET", "POST"])
def comparaciones(request):
    """CU-05."""
    origen = request.data if request.method == "POST" else request.query_params
    run_a, run_b = origen.get("run_a"), origen.get("run_b")
    if not run_a or not run_b:
        return Response({"detalle": "hacen falta run_a y run_b"}, status=400)
    return Response(agregados.comparar(_run(run_a), _run(run_b)))


@api_view(["GET"])
def kpis_barrido(request):
    filas = ScenarioRunKpi.objects.select_related(
        "simulation_run", "simulation_run__scenario"
    ).order_by("simulation_run__run_id")
    escenario = request.query_params.get("escenario")
    if escenario:
        filas = filas.filter(simulation_run__scenario__codigo=escenario)
    return Response(ScenarioRunKpiSerializer(filas, many=True).data)


@api_view(["GET"])
def exportar_tabla(request, identificador, tabla):
    """Exportacion CSV de una tabla filtrada (criterio de aceptacion 7)."""
    if tabla not in TABLAS_EXPORTABLES:
        return Response(
            {"detalle": f"tabla desconocida, opciones: {', '.join(TABLAS_EXPORTABLES)}"},
            status=400,
        )

    run = _run(identificador)
    modelo, serializer_class = TABLAS_EXPORTABLES[tabla]
    filas = modelo.objects.filter(simulation_run=run)

    aplicados = []
    for campo, valor in request.query_params.items():
        if campo in {f.name for f in modelo._meta.get_fields() if hasattr(f, "name")}:
            filas = filas.filter(**{campo: valor})
            aplicados.append(f"{campo}-{valor}")

    datos = serializer_class(filas, many=True).data
    # El filtro va en el nombre: dos exportaciones distintas de la misma tabla no pueden bajar
    # con el mismo archivo.
    sufijo = "_" + "_".join(slugify(a) for a in aplicados) if aplicados else ""
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = (
        f'attachment; filename="{run.run_id}_{tabla}{sufijo}.csv"'
    )

    if not datos:
        return respuesta

    columnas = [c for c in datos[0] if c != "extra"]
    escritor = csv.DictWriter(respuesta, fieldnames=columnas, extrasaction="ignore")
    escritor.writeheader()
    for fila in datos:
        escritor.writerow({c: fila.get(c) for c in columnas})
    return respuesta
