import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.models import ImportBatch

from .importadores import ImportacionRechazada, importar_kpis_barrido, importar_paquete_auditoria
from .serializers import ImportBatchSerializer

logger = logging.getLogger(__name__)


class ImportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ImportBatch.objects.select_related("simulation_run").prefetch_related("archivos")
    serializer_class = ImportBatchSerializer

    @action(
        detail=False,
        methods=["post"],
        url_path="upload",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload(self, request):
        """CU-01 y CU-02: paquete de auditoria (.zip) o `kpis_por_corrida.csv`."""
        archivo = request.FILES.get("archivo")
        if archivo is None:
            return Response(
                {"detalle": "falta el archivo (campo 'archivo')"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        contenido = archivo.read()
        nombre = archivo.name

        try:
            if nombre.lower().endswith(".zip"):
                lote = importar_paquete_auditoria(contenido, nombre)
            elif nombre.lower().endswith(".csv"):
                lote = importar_kpis_barrido(contenido, nombre)
            else:
                return Response(
                    {
                        "detalle": "formato no reconocido: se espera un .zip con el paquete de "
                        "auditoria o kpis_por_corrida.csv"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ImportacionRechazada as exc:
            return Response(
                {"estado": "RECHAZADA", "mensajes": exc.mensajes},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception as exc:  # noqa: BLE001 - con DEBUG=0 el 500 llega como HTML sin causa
            logger.exception("fallo la importacion de %s", nombre)
            return Response(
                {
                    "estado": "FALLIDA",
                    "mensajes": [
                        {
                            "nivel": "ERROR",
                            "texto": f"la importacion fallo por un error inesperado: "
                            f"{type(exc).__name__}: {exc}",
                        }
                    ],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            ImportBatchSerializer(lote).data,
            status=status.HTTP_201_CREATED,
        )
