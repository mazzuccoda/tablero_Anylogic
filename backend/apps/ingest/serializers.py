from rest_framework import serializers

from apps.core.models import ImportBatch, ImportedFile


class ImportedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportedFile
        fields = ["nombre", "tabla", "checksum_sha256", "filas_importadas", "filas_manifiesto"]


class ImportBatchSerializer(serializers.ModelSerializer):
    archivos = ImportedFileSerializer(many=True, read_only=True)
    run_id = serializers.CharField(source="simulation_run.run_id", default="", read_only=True)
    simulation_run_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "estado",
            "run_id",
            "simulation_run_id",
            "version_esquema",
            "mensajes",
            "filas_por_tabla",
            "archivos",
            "creado",
        ]
