from django.apps import AppConfig
from wagtail.images.apps import WagtailImagesAppConfig


class HomeAppConfig(AppConfig):
    name = "home"

    def ready(self):
        import home.signals  # noqa: F401


class CustomImagesAppConfig(WagtailImagesAppConfig):
    default_attrs = {"decoding": "async", "loading": "lazy"}
