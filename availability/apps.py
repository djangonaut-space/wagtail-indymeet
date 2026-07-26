from django.apps import AppConfig

from availability import checks  # noqa: F401


class AvailabilityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "availability"
    verbose_name = "Availability"
