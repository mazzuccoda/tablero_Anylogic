from django.urls import path

from . import views

urlpatterns = [
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
