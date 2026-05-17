from django.apps import AppConfig
from wagtail.images.apps import WagtailImagesAppConfig


class HomeAppConfig(AppConfig):
    name = "home"


class CustomImagesAppConfig(WagtailImagesAppConfig):
    default_attrs = {"decoding": "async", "loading": "lazy"}
