from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"estado": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.ingest.urls")),
    path("api/v1/", include("apps.dashboard.urls")),
]
