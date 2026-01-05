from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework.serializers import SerializerMethodField

from talks.models import Talk


class TalkGeoSerializer(GeoFeatureModelSerializer):
    speakers_list = SerializerMethodField()

    class Meta:
        model = Talk
        geo_field = "location"
        fields = (
            "title",
            "date",
            "event_name",
            "talk_type",
            "speakers_list",
            "video_link",
        )
        id_field = None

    def get_speakers_list(self, obj):
        return ", ".join(
            [s.speaker.username.lower().capitalize() for s in obj.speakers.all()]
        )
