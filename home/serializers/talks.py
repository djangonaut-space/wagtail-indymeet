from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework.serializers import SerializerMethodField
from django.utils.safestring import mark_safe

from home.models.talk import Talk


class TalkGeoSerializer(GeoFeatureModelSerializer):
    speakers_list = SerializerMethodField()
    popup_html = SerializerMethodField()

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
            "popup_html",
        )
        id_field = None

    def get_speakers_list(self, obj):
        return obj.get_speakers_names()

    def get_popup_html(self, obj):
        video_html = (
            f"""
            <a href="${obj.video_link}" target="_blank" aria-label="Watch talk recording">
                <span aria-hidden="true">📹</span> Talk recording
            </a>"""
            if obj.video_link
            else ""
        )
        return mark_safe(f"""
            <strong>{obj.title}</strong><br/>
            <b>{obj.event_name}</b> - {obj.date.year}<br>
            {obj.get_speakers_names()}<br>
            {video_html}
        """)
