from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, ScenarioViewSet, SimulationRunViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("scenarios", ScenarioViewSet, basename="scenario")
router.register("simulation-runs", SimulationRunViewSet, basename="simulationrun")

urlpatterns = router.urls
