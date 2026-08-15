"""Filtros del Cost Explorer.

El recorte se arma desde una lista blanca de campos: la API no acepta nombres de campo libres, asi
que no se puede pedir un `values()` arbitrario ni filtrar por una relacion. Cada respuesta devuelve
`filtros_aplicados` para que un numero copiado a una presentacion se pueda reproducir despues.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import QuerySet

from apps.core.models import TipoContable

from .clasificacion import ETAPA_NO_CLASIFICADA, ETAPA_POR_CATEGORIA, categorias_de_etapa

CAMPOS_EXACTOS = (
    "tipo_contable",
    "categoria",
    "producto",
    "material",
    "proveedor",
    "circuito",
    "origen",
    "destino",
    "sitio",
    "alcance",
    "unidad",
    "codigo_pedido",
    "id_asignacion",
    "id_contenedor",
    "id_lote",
    "motivo",
)


class FiltroInvalido(ValueError):
    """Un parametro no esta en la lista blanca o no se puede interpretar."""


def _numero(nombre: str, valor: str) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
        raise FiltroInvalido(f"{nombre} tiene que ser un numero, llego {valor!r}") from exc


@dataclass
class FiltrosCostos:
    """Recorte de `costos_eventos`.

    `tipo_contable` arranca en `CAJA` porque es la unica serie que suma plata; para ver el costo de
    oportunidad hay que pedir `ECONOMICO` explicitamente. Nunca se devuelven las dos juntas.
    """

    tipo_contable: str = TipoContable.CAJA
    exactos: dict[str, str] = field(default_factory=dict)
    etapa: str = ""
    dia_desde: float | None = None
    dia_hasta: float | None = None

    @classmethod
    def desde_query_params(cls, params) -> FiltrosCostos:
        ignorados = {"run_id", "limit", "offset", "orden", "formato", "escenario"}
        exactos: dict[str, str] = {}
        tipo_contable = TipoContable.CAJA
        etapa = ""
        dia_desde = dia_hasta = None

        for nombre, valor in params.items():
            if nombre in ignorados or valor == "":
                continue
            if nombre == "tipo_contable":
                tipo_contable = cls._tipo_contable(valor)
            elif nombre == "etapa":
                etapa = cls._etapa(valor)
            elif nombre == "dia_desde":
                dia_desde = _numero(nombre, valor)
            elif nombre == "dia_hasta":
                dia_hasta = _numero(nombre, valor)
            elif nombre in CAMPOS_EXACTOS:
                exactos[nombre] = valor
            else:
                raise FiltroInvalido(
                    f"filtro desconocido {nombre!r}; opciones: "
                    f"{', '.join([*CAMPOS_EXACTOS, 'etapa', 'dia_desde', 'dia_hasta'])}"
                )

        if dia_desde is not None and dia_hasta is not None and dia_desde > dia_hasta:
            raise FiltroInvalido(f"dia_desde ({dia_desde}) es mayor que dia_hasta ({dia_hasta})")

        return cls(
            tipo_contable=tipo_contable,
            exactos=exactos,
            etapa=etapa,
            dia_desde=dia_desde,
            dia_hasta=dia_hasta,
        )

    @staticmethod
    def _tipo_contable(valor: str) -> str:
        candidato = valor.strip().upper()
        if candidato not in TipoContable.values:
            raise FiltroInvalido(
                f"tipo_contable tiene que ser uno de {', '.join(TipoContable.values)}"
            )
        return candidato

    @staticmethod
    def _etapa(valor: str) -> str:
        candidato = valor.strip().upper()
        etapas = {*ETAPA_POR_CATEGORIA.values(), ETAPA_NO_CLASIFICADA}
        if candidato not in etapas:
            raise FiltroInvalido(
                f"etapa desconocida {valor!r}; opciones: {', '.join(sorted(etapas))}"
            )
        return candidato

    def aplicar(self, queryset: QuerySet) -> QuerySet:
        return aplicar_filtros_costos(queryset, self)

    def como_dict(self) -> dict:
        aplicados: dict[str, object] = {"tipo_contable": self.tipo_contable}
        aplicados.update(self.exactos)
        if self.etapa:
            aplicados["etapa"] = self.etapa
        if self.dia_desde is not None:
            aplicados["dia_desde"] = self.dia_desde
        if self.dia_hasta is not None:
            aplicados["dia_hasta"] = self.dia_hasta
        return aplicados


def aplicar_filtros_costos(queryset: QuerySet, filtros: FiltrosCostos) -> QuerySet:
    """Aplica el recorte sobre un queryset de `CostCharge`.

    La etapa no es una columna: se traduce a las categorias que el mapa asigna a esa etapa, y
    `ETAPA_NO_CLASIFICADA` es "toda categoria que el mapa no conoce". Asi el filtro no necesita
    migracion ni una columna derivada que habria que mantener sincronizada con la clasificacion.
    """
    queryset = queryset.filter(tipo_contable=filtros.tipo_contable)

    for campo, valor in filtros.exactos.items():
        if campo not in CAMPOS_EXACTOS:
            raise FiltroInvalido(f"filtro desconocido {campo!r}")
        queryset = queryset.filter(**{campo: valor})

    if filtros.etapa == ETAPA_NO_CLASIFICADA:
        queryset = queryset.exclude(categoria__in=sorted(ETAPA_POR_CATEGORIA))
    elif filtros.etapa:
        queryset = queryset.filter(categoria__in=categorias_de_etapa(filtros.etapa))

    if filtros.dia_desde is not None:
        queryset = queryset.filter(dia__gte=filtros.dia_desde)
    if filtros.dia_hasta is not None:
        queryset = queryset.filter(dia__lte=filtros.dia_hasta)

    return queryset
