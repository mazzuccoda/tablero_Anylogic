from rest_framework import viewsets

from .models import Project, Scenario, SimulationRun
from .serializers import ProjectSerializer, ScenarioSerializer, SimulationRunSerializer


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class ScenarioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Scenario.objects.select_related("project")
    serializer_class = ScenarioSerializer
    filterset_fields = ["project", "codigo"]


class SimulationRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SimulationRun.objects.select_related("scenario")
    serializer_class = SimulationRunSerializer
    filterset_fields = ["scenario", "tipo", "run_id"]
    lookup_value_regex = "[^/]+"

    def get_object(self):
        """Permite `/simulation-runs/E-00-R0/` ademas del id numerico."""
        valor = self.kwargs[self.lookup_field]
        if str(valor).isdigit():
            return super().get_object()
        obj = self.get_queryset().get(run_id=valor)
        self.check_object_permissions(self.request, obj)
        return obj
