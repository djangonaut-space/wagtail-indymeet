"""django-allauth adapters: the hooks where allauth defers to this project."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import Http404
from django.http import HttpRequest
from django.urls import reverse

from home.email import allowed_recipients


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        """Apply the project's rule about who may be emailed outside production."""
        if allowed_recipients([email]):
            super().send_mail(template_prefix, email, context)

    def send_notification_mail(
        self,
        template_prefix: str,
        user: AbstractBaseUser,
        context: dict | None = None,
        email: str | None = None,
    ) -> None:
        """
        Send security notifications to the address on the user record.

        allauth would otherwise use its own copy of the address, which lags
        behind when an email is changed without the profile being saved.
        """
        super().send_notification_mail(
            template_prefix, user, context=context, email=email or user.email
        )

    def get_password_change_redirect_url(self, request: HttpRequest) -> str:
        return reverse("profile")


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_app(
        self, request: HttpRequest, provider: str, client_id: str | None = None
    ) -> SocialApp:
        """Treat GitHub sign-in as missing, not broken, when it isn't configured."""
        try:
            return super().get_app(request, provider, client_id=client_id)
        except SocialApp.DoesNotExist as error:
            raise Http404("This sign-in method is not configured.") from error
