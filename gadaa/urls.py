from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("", include("ops.urls")),
]

handler403 = "core.views.permission_denied"
