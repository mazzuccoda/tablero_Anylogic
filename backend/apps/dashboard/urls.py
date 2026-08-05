from django.urls import path

from . import views
from .cost_explorer import views as cost_explorer

urlpatterns = [
    path(
        "simulation-runs/<str:identificador>/cost-explorer/summary/",
        cost_explorer.resumen,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/by-stage/",
        cost_explorer.por_etapa,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/by-category/",
        cost_explorer.por_categoria,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/waterfall/",
        cost_explorer.waterfall,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/by-arc/",
        cost_explorer.por_arco,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/by-dimension/<str:dimension>/",
        cost_explorer.por_dimension,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/by-object/<str:objeto>/",
        cost_explorer.por_objeto,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/events/",
        cost_explorer.eventos,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/constraints/",
        cost_explorer.sobrecosto_por_restriccion,
    ),
    path(
        "simulation-runs/<str:identificador>/cost-explorer/reconciliation/",
        cost_explorer.reconciliar,
    ),
    path("simulation-runs/<str:identificador>/dashboard/", views.dashboard_corrida),
    path("simulation-runs/<str:identificador>/inventory/", views.inventario_corrida),
    path("simulation-runs/<str:identificador>/costs/", views.costos_corrida),
    path("simulation-runs/<str:identificador>/capacity/", views.capacidad_corrida),
    path("simulation-runs/<str:identificador>/decisions/", views.decisiones_corrida),
    path("simulation-runs/<str:identificador>/export/<str:tabla>/", views.exportar_tabla),
    path("orders/<str:codigo_pedido>/why/", views.por_que_pedido),
    path("comparisons/", views.comparaciones),
    path("sweep-kpis/", views.kpis_barrido),
]
