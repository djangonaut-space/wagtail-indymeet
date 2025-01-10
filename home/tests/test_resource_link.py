from django.test import TestCase
from django.urls import reverse

from home.factories import ResourceLinkFactory


class ResourceLinkViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resource_link = ResourceLinkFactory.create()
        cls.url = reverse("resource_link", kwargs={"path": cls.resource_link.path})

    def test_get(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, self.resource_link.url, fetch_redirect_response=False
        )

    def test_get_not_found(self):
        response = self.client.get(
            reverse("resource_link", kwargs={"path": "not-found"})
        )
        self.assertEqual(response.status_code, 404)

    def test_post(self):
        response = self.client.post(self.url)
        self.assertRedirects(
            response, self.resource_link.url, fetch_redirect_response=False
        )
