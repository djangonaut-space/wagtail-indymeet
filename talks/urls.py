from django.urls import path
from .views import TalkGeoJSONView, TalkMapView

urlpatterns = [
    path("api/geojson/", TalkGeoJSONView.as_view(), name="talks_geojson"),
    path("map/", TalkMapView.as_view(), name="talks_map"),
]
