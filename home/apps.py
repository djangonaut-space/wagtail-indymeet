from django.apps import AppConfig
from wagtail.images.apps import WagtailImagesAppConfig
from wagtail import hooks


class HomeAppConfig(AppConfig):
    name = "home"

    def ready(self):
        from wagtail.admin.userbar import AccessibilityItem

        @hooks.register("construct_wagtail_userbar")
        def remove_frontend_accessibility_checks(request, items, page=None):
            """
            The accessibility checker renders some content that caused things to appear
            wonky and lead to wasted time debugging. Removing for now.
            """
            items[:] = [
                item
                for item in items
                if not (isinstance(item, AccessibilityItem) and not item.in_editor)
            ]


class CustomImagesAppConfig(WagtailImagesAppConfig):
    default_attrs = {"decoding": "async", "loading": "lazy"}
