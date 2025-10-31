from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        """Import custom lookups when the app is ready."""
        import accounts.lookups  # noqa: F401
