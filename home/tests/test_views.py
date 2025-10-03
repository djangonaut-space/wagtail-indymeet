from django.test import TestCase


class WagtailHomePageTests(TestCase):

    def test_home_page(self):
        response = self.client.get("/")
        assert response.status_code == 200
        self.assertTemplateUsed(response, "home/home_page.html")
