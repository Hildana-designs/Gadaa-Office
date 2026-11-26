from django.urls import path

from ops import views
from ops.resources import ALL

app_name = "ops"
urlpatterns = [path("trips/<int:pk>/view/", views.trip_detail, name="trip_detail")]
for resource in ALL:
    urlpatterns += resource.urls()
