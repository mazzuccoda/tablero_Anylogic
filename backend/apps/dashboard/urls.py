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
    path(
        "simulation-runs/<str:identificador>/costs/cintas/",
        cost_explorer.cintas,
    ),
    path(
        "simulation-runs/<str:identificador>/almacenamiento/por-producto/",
        cost_explorer.almacenaje_por_producto,
    ),
    path(
        "simulation-runs/<str:identificador>/almacenamiento/depositos/",
        cost_explorer.almacenaje_depositos,
    ),
    path(
        "simulation-runs/<str:identificador>/almacenamiento/top-lotes/",
        cost_explorer.top_lotes,
    ),
    path(
        "simulation-runs/<str:identificador>/depositos/<str:ubicacion>/flujo-y-decision/",
        cost_explorer.deposito_flujo_y_decision,
    ),
    path(
        "simulation-runs/<str:identificador>/depositos/<str:ubicacion>/stock-diario/",
        cost_explorer.deposito_stock_diario,
    ),
    path(
        "simulation-runs/<str:identificador>/lotes/<str:id_lote>/recorrido/",
        cost_explorer.recorrido_de_lote,
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
