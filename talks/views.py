from django.contrib.gis.geos import Point

from django.views.generic import TemplateView
from talks.models import Talk
from django.db import models
from rest_framework.generics import ListAPIView

from talks.serializers import TalkGeoSerializer


class TalkMapView(TemplateView):
    template_name = "talks/talk_map.html"


class TalkGeoJSONView(ListAPIView):
    serializer_class = TalkGeoSerializer

    def get_queryset(self):
        return Talk.objects.exclude(
            models.Q(location__isnull=True) | models.Q(location=Point(0, 0, srid=4326))
        ).prefetch_related("speakers__speaker")
