from http import HTTPStatus

from django.contrib.admin.sites import AdminSite
from django.contrib.admin.sites import all_sites
from django.db.models import Model
from django.test import TestCase
from django.urls import reverse
from unittest_parametrize import param
from unittest_parametrize import parametrize
from unittest_parametrize import ParametrizedTestCase

from accounts.models import CustomUser

each_model_admin = parametrize(
    "site,model,model_admin",
    [
        param(
            site,
            model,
            model_admin,
            id=f"{site.name}_{str(model_admin).replace('.', '_')}",
        )
        for site in all_sites
        for model, model_admin in site._registry.items()
    ],
)


class ModelAdminTests(ParametrizedTestCase, TestCase):
    user: CustomUser

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def make_url(self, site: AdminSite, model: type[Model], page: str) -> str:
        return reverse(
            f"{site.name}:{model._meta.app_label}_{model._meta.model_name}_{page}"
        )

    @each_model_admin
    def test_changelist(self, site, model, model_admin):
        url = self.make_url(site, model, "changelist")
        response = self.client.get(url, {"q": "example.com"})
        assert response.status_code == HTTPStatus.OK

    @each_model_admin
    def test_add(self, site, model, model_admin):
        url = self.make_url(site, model, "add")
        response = self.client.get(url)
        assert response.status_code in (
            HTTPStatus.OK,
            HTTPStatus.FORBIDDEN,  # some admin classes blanket disallow "add"
        )
