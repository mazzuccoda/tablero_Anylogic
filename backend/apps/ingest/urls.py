from rest_framework.routers import DefaultRouter

from .views import ImportViewSet

router = DefaultRouter()
router.register("imports", ImportViewSet, basename="import")

urlpatterns = router.urls
