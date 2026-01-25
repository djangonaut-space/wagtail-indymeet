from django.test import TestCase
from django.urls import reverse

from home.tests.test_models import TalksBaseData


class WagtailHomePageTests(TestCase):

    def test_home_page(self):
        response = self.client.get("/")
        assert response.status_code == 200
        self.assertTemplateUsed(response, "home/home_page.html")


class TalkMapViewTests(TalksBaseData):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.globe_url = reverse("talks_map")
        cls.talks_api_url = reverse("talks_geojson")

    def test_talks_map_url(self):
        self.assertEqual(self.globe_url, "/talks/map/")

    def test_talks_geojson_url(self):
        self.assertEqual(self.talks_api_url, "/talks/api/geojson/")

    def test_talks_map_page(self):
        response = self.client.get(self.globe_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/talks/talk_map.html")
        # Assert importmap references
        content = response.content.decode()
        self.assertIn("three", content)
        self.assertIn("three/addons/", content)
        self.assertIn("earthTextureUrl", content)

    def test_talks_geojson_page(self):
        def normalize_html(props):
            return {
                k: " ".join(v.split()) if k == "popup_html" else v
                for k, v in props.items()
            }

        response = self.client.get(self.talks_api_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["content-type"], "application/json")
        data = response.json()
        self.assertEqual(data["type"], "FeatureCollection")
        # Only the talk with the location point is shown in the geojson
        self.assertEqual(len(data["features"]), 1)
        self.assertEqual(
            data["features"][0]["geometry"],
            {"type": "Point", "coordinates": [-117.75, 34.05]},
        )
        expected_props = {
            "title": "Test on-site Talk",
            "date": "2026-01-25",
            "event_name": "Test Event",
            "talk_type": "on_site",
            "speakers_list": "Jane Doe, speAKer",
            "video_link": "",
            "popup_html": " ".join(
                """
                    <strong>Test on-site Talk</strong><br/>
                    <b>Test Event</b> - 2026<br> Jane Doe, speAKer<br>
                """.split()
            ),
        }

        properties = data["features"][0]["properties"]
        self.assertEqual(normalize_html(properties), expected_props)
