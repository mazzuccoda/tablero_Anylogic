from rest_framework import serializers

from .models import (
    ArcExecution,
    AssignmentResult,
    CostCharge,
    DecisionAlternative,
    InventorySnapshot,
    Project,
    ResourceCapacitySnapshot,
    Scenario,
    ScenarioRunKpi,
    SimulationRun,
)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "nombre", "descripcion", "creado"]


class ScenarioSerializer(serializers.ModelSerializer):
    project_nombre = serializers.CharField(source="project.nombre", read_only=True)
    corridas = serializers.IntegerField(source="runs.count", read_only=True)

    class Meta:
        model = Scenario
        fields = ["id", "codigo", "descripcion", "project", "project_nombre", "corridas", "creado"]


class SimulationRunSerializer(serializers.ModelSerializer):
    escenario = serializers.CharField(source="scenario.codigo", read_only=True)
    tiene_drill_down = serializers.BooleanField(read_only=True)

    class Meta:
        model = SimulationRun
        fields = [
            "id",
            "run_id",
            "escenario",
            "replica",
            "tipo",
            "nivel_auditoria",
            "version_esquema",
            "version_modelo",
            "duracion_campania_dias",
            "fecha_inicio_campania",
            "generado",
            "importado",
            "tiene_drill_down",
        ]


class DecisionAlternativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionAlternative
        exclude = ["simulation_run"]


class AssignmentResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentResult
        exclude = ["simulation_run"]


class ArcExecutionSerializer(serializers.ModelSerializer):
    duracion_esperada_aplica = serializers.BooleanField(read_only=True)

    class Meta:
        model = ArcExecution
        exclude = ["simulation_run"]


class CostChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCharge
        exclude = ["simulation_run"]


class InventorySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventorySnapshot
        exclude = ["simulation_run", "extra"]


class ResourceCapacitySnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceCapacitySnapshot
        exclude = ["simulation_run", "extra"]


class ScenarioRunKpiSerializer(serializers.ModelSerializer):
    run_id = serializers.CharField(source="simulation_run.run_id", read_only=True)
    escenario = serializers.CharField(source="simulation_run.scenario.codigo", read_only=True)
    replica = serializers.IntegerField(source="simulation_run.replica", read_only=True)

    class Meta:
        model = ScenarioRunKpi
        fields = ["run_id", "escenario", "replica", "semilla", "valores"]
