from django.views.generic import TemplateView
from home.constants import NULL_ISLAND
from django.db import models
from rest_framework.generics import ListAPIView
from django.templatetags.static import static

from home.models.talk import Talk
from home.serializers.talks import TalkGeoSerializer


class TalkMapView(TemplateView):
    template_name = "home/talks/talk_map.html"


class TalkGeoJSONView(ListAPIView):
    serializer_class = TalkGeoSerializer

    def get_queryset(self):
        return Talk.objects.exclude(
            models.Q(location__isnull=True) | models.Q(location=NULL_ISLAND)
        ).prefetch_related("speakers__speaker")
