"""Cost Explorer (MOD v3.2).

Navega el costo de la red desde el total hasta el evento contable. Tres reglas que vienen del
modelo y no de esta plataforma:

- los importes salen **solo** de `costos_eventos`; nada se recalcula desde tarifas si el paquete ya
  trajo `importe_usd` (ADR-064);
- `CAJA` y `ECONOMICO` no se suman nunca: el segundo es costo de oportunidad;
- el USD/tn no se calcula dividiendo por la suma de `cantidad` (mezcla toneladas-dia con viajes y
  contenedores) sino por las toneladas del **objeto de costo**, y cada valor viaja con la base
  fisica que uso.
"""

from .agregados import costos_por_categoria, costos_por_etapa, resumen_costos
from .clasificacion import (
    ETAPA_NO_CLASIFICADA,
    ETAPA_POR_CATEGORIA,
    clasificar_etapa,
    tipo_geografia,
)
from .filtros import FiltrosCostos, aplicar_filtros_costos
from .objetos import (
    toneladas_entregadas,
    toneladas_por_contenedor,
    toneladas_por_lote,
    toneladas_por_pedido,
)
from .reconciliacion import reconciliar_costos

__all__ = [
    "ETAPA_NO_CLASIFICADA",
    "ETAPA_POR_CATEGORIA",
    "FiltrosCostos",
    "aplicar_filtros_costos",
    "clasificar_etapa",
    "costos_por_categoria",
    "costos_por_etapa",
    "reconciliar_costos",
    "resumen_costos",
    "tipo_geografia",
    "toneladas_entregadas",
    "toneladas_por_contenedor",
    "toneladas_por_lote",
    "toneladas_por_pedido",
]
