from django.apps import AppConfig
from wagtail.images.apps import WagtailImagesAppConfig


class HomeAppConfig(AppConfig):
    name = "home"

    def ready(self):
        from home import receivers


class CustomImagesAppConfig(WagtailImagesAppConfig):
    default_attrs = {"decoding": "async", "loading": "lazy"}
