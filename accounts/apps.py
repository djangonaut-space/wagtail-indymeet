from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        """Import custom lookups and receivers when the app is ready."""
        from accounts import lookups, receivers  # noqa: F401
