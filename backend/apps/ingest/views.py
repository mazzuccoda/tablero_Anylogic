from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.models import ImportBatch

from .importadores import ImportacionRechazada, importar_kpis_barrido, importar_paquete_auditoria
from .serializers import ImportBatchSerializer


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

        return Response(
            ImportBatchSerializer(lote).data,
            status=status.HTTP_201_CREATED,
        )
