"""Views for managing two-factor authentication from a user's profile."""

from typing import Any

from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import View
from django.views.generic import TemplateView
from django.views.generic.edit import FormView
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from . import two_factor
from .forms import PasswordConfirmationForm
from .forms import TwoFactorSetupForm
from .forms import TwoFactorVerifyForm

RECOVERY_CODES_TEMPLATE = "registration/two_factor_recovery_codes.html"
SWITCH_ACCOUNT_PARAM = "switch_account"
RECOVERY_TOKEN_SESSION_KEY = "two_factor_recovery_token"
# Stands in for the token in the recovery URL once it is held in the session.
RECOVERY_URL_PLACEHOLDER = "confirm"


class TwoFactorView(LoginRequiredMixin, TemplateView):
    """Show whether two-factor authentication is on and link to the actions."""

    template_name = "registration/two_factor.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        user = self.request.user
        return super().get_context_data(
            **kwargs,
            two_factor_enabled=two_factor.has_two_factor(user),
            remaining_recovery_codes=two_factor.remaining_recovery_codes(user),
            two_factor_required=two_factor.is_required(),
            two_factor_required_from=two_factor.required_from(),
            recovery_code_count=two_factor.RECOVERY_CODE_COUNT,
        )


@method_decorator(sensitive_post_parameters("password", "token"), name="dispatch")
@method_decorator(never_cache, name="dispatch")
class TwoFactorSetupView(LoginRequiredMixin, FormView):
    """
    Enrol an authenticator app.

    The page shows the secret for a pending device; it only starts counting as
    two-factor authentication once the user proves their app generates valid
    codes, so a half-finished setup can never lock anyone out.
    """

    template_name = "registration/two_factor_setup.html"
    form_class = TwoFactorSetupForm

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated and two_factor.has_two_factor(request.user):
            messages.info(request, _("Two-factor authentication is already enabled."))
            return redirect("two_factor")
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def device(self) -> TOTPDevice:
        return two_factor.get_or_create_pending_device(self.request.user)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["device"] = self.device
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(
            **kwargs,
            qr_code=two_factor.get_qr_code_data_uri(self.device),
            manual_entry_key=two_factor.get_manual_entry_key(self.device),
        )

    def form_valid(self, form: TwoFactorSetupForm) -> HttpResponse:
        recovery_codes = two_factor.enable_two_factor(self.device)
        two_factor.send_two_factor_changed_email(
            self.request.user, two_factor.CHANGE_ENABLED
        )
        messages.success(self.request, _("Two-factor authentication is now enabled."))
        return render(
            self.request,
            RECOVERY_CODES_TEMPLATE,
            {"recovery_codes": recovery_codes},
        )


class TwoFactorEnabledRequiredMixin(LoginRequiredMixin):
    """Send users without two-factor authentication back to the overview page."""

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated and not two_factor.has_two_factor(
            request.user
        ):
            messages.info(request, _("Two-factor authentication is not enabled."))
            return redirect("two_factor")
        return super().dispatch(request, *args, **kwargs)


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class PasswordConfirmationView(TwoFactorEnabledRequiredMixin, FormView):
    """Base for two-factor changes that only need the password re-entered."""

    template_name = "registration/two_factor_confirm.html"
    form_class = PasswordConfirmationForm

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


@method_decorator(never_cache, name="dispatch")
class TwoFactorRecoveryCodesView(PasswordConfirmationView):
    """Replace the user's recovery codes and show the new set once."""

    extra_context = {
        "heading": _("Generate new recovery codes"),
        "description": _(
            "Your existing recovery codes will stop working immediately and be "
            "replaced with a new set."
        ),
        "submit_label": _("Generate new codes"),
    }

    def form_valid(self, form: PasswordConfirmationForm) -> HttpResponse:
        recovery_codes = two_factor.generate_recovery_codes(self.request.user)
        two_factor.send_two_factor_changed_email(
            self.request.user, two_factor.CHANGE_RECOVERY_CODES
        )
        return render(
            self.request,
            RECOVERY_CODES_TEMPLATE,
            {"recovery_codes": recovery_codes},
        )


class TwoFactorDisableView(PasswordConfirmationView):
    """
    Turn two-factor authentication off.

    Once two-factor authentication is mandatory this is how a user moves to a
    new authenticator app: the old one is removed and
    ``RequireTwoFactorMiddleware`` sends them straight back to the setup page.
    """

    success_url = reverse_lazy("two_factor")
    extra_context = {
        "heading": _("Turn off two-factor authentication"),
        "description": _(
            "Your account will be protected by your password alone. Your "
            "authenticator app and recovery codes will stop working."
        ),
        "submit_label": _("Turn off two-factor authentication"),
        "destructive": True,
    }
    required_extra_context = {
        "heading": _("Replace your authenticator app"),
        "description": _(
            "Your current authenticator app and recovery codes will stop "
            "working, and you will set up a new authenticator app straight away."
        ),
        "submit_label": _("Remove and set up again"),
    }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if two_factor.is_required():
            context.update(self.required_extra_context)
        return context

    def form_valid(self, form: PasswordConfirmationForm) -> HttpResponse:
        two_factor.disable_two_factor(self.request.user)
        two_factor.send_two_factor_changed_email(
            self.request.user, two_factor.CHANGE_DISABLED
        )
        if two_factor.is_required():
            return redirect("two_factor_setup")
        messages.success(
            self.request, _("Two-factor authentication has been turned off.")
        )
        return super().form_valid(form)


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
@method_decorator(never_cache, name="dispatch")
class TwoFactorRecoverView(FormView):
    """
    Let a locked-out user reset two-factor authentication from an emailed link.

    The link is only ever sent by a superuser (see ``CustomUserAdmin``), and
    the user must still enter their password, so neither the inbox nor the
    password alone is enough to remove the second factor.

    As with Django's password reset, the token is moved into the session and
    the browser redirected to a URL without it, so it isn't left in the address
    bar, browser history, or reported to analytics as the page URL.
    """

    template_name = "registration/two_factor_confirm.html"
    form_class = PasswordConfirmationForm
    extra_context = {
        "heading": _("Reset two-factor authentication"),
        "description": _(
            "Enter your password to remove your current authenticator app and "
            "recovery codes. You will then set up a new authenticator app."
        ),
        "submit_label": _("Reset two-factor authentication"),
        "hide_cancel": True,
    }

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        token = kwargs["token"]
        if token == RECOVERY_URL_PLACEHOLDER:
            token = request.session.get(RECOVERY_TOKEN_SESSION_KEY, "")
        elif two_factor.get_user_for_recovery_token(token) is not None:
            request.session[RECOVERY_TOKEN_SESSION_KEY] = token
            return redirect("two_factor_recover", token=RECOVERY_URL_PLACEHOLDER)
        self.recovering_user = two_factor.get_user_for_recovery_token(token)
        if self.recovering_user is None:
            request.session.pop(RECOVERY_TOKEN_SESSION_KEY, None)
            messages.error(
                request,
                _(
                    "This recovery link is invalid or has expired. Contact "
                    "hello@djangonaut.space to ask for a new one."
                ),
            )
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.recovering_user
        return kwargs

    def form_valid(self, form: PasswordConfirmationForm) -> HttpResponse:
        user = authenticate(
            self.request,
            username=self.recovering_user.get_username(),
            password=form.cleaned_data["password"],
        )
        if user is None:
            form.add_error("password", _("Incorrect password."))
            return self.form_invalid(form)
        two_factor.disable_two_factor(user)
        two_factor.clear_pending_login(self.request)
        self.request.session.pop(RECOVERY_TOKEN_SESSION_KEY, None)
        auth_login(self.request, user)
        two_factor.send_two_factor_changed_email(user, two_factor.CHANGE_RESET)
        messages.success(
            self.request,
            _(
                "Two-factor authentication has been reset. Set up your new "
                "authenticator app now."
            ),
        )
        return redirect("two_factor_setup")


class TwoFactorLoginView(LoginView):
    """
    The password step of logging in.

    Users without two-factor authentication are logged in as usual. Users with
    it are *not* logged in here: the accepted password is noted in the session
    and they are sent to ``TwoFactorVerifyView`` to enter a code.

    Signed-in users are redirected onwards, unless ``SWITCH_ACCOUNT_PARAM`` is
    in the query string, which shows the form so they can change account.
    """

    redirect_authenticated_user = True

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if SWITCH_ACCOUNT_PARAM in request.GET:
            self.redirect_authenticated_user = False
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: AuthenticationForm) -> HttpResponse:
        user = form.get_user()
        if not two_factor.has_two_factor(user):
            return super().form_valid(form)
        two_factor.set_pending_login(self.request, user, self.get_success_url())
        return redirect("two_factor_verify")


@method_decorator(sensitive_post_parameters("token"), name="dispatch")
@method_decorator(never_cache, name="dispatch")
class TwoFactorVerifyView(FormView):
    """The code step of logging in, which completes the login."""

    template_name = "registration/two_factor_verify.html"
    form_class = TwoFactorVerifyForm

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.pending_login = two_factor.get_pending_login(request)
        if self.pending_login is None:
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.pending_login.user
        return kwargs

    def form_valid(self, form: TwoFactorVerifyForm) -> HttpResponse:
        pending = self.pending_login
        two_factor.clear_pending_login(self.request)
        auth_login(self.request, pending.user, backend=pending.backend)
        otp_login(self.request, form.device)
        if isinstance(form.device, StaticDevice):
            remaining = two_factor.remaining_recovery_codes(pending.user)
            messages.warning(
                self.request,
                ngettext(
                    "You logged in with a recovery code. You have %(count)d "
                    "recovery code left.",
                    "You logged in with a recovery code. You have %(count)d "
                    "recovery codes left.",
                    remaining,
                )
                % {"count": remaining},
            )
        return redirect(pending.redirect_url)


class AdminLoginRedirectView(View):
    """
    Replace an admin site's own login page with the main login.

    The Wagtail and Django admins each ship a password-only login form, which
    would let a user skip their two-factor code. Mounting this view over those
    URLs leaves ``TwoFactorLoginView`` as the only way to log in.

    A signed-in user without admin access is sent to the main login with
    ``SWITCH_ACCOUNT_PARAM`` so they can log in as someone else, as the admin
    login pages allowed. Without it the main login would bounce them straight
    back here and loop.
    """

    admin_index: str = ""
    # Permission that grants access to the admin; staff status when unset.
    access_permission: str | None = None

    def get(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        params = {
            REDIRECT_FIELD_NAME: request.GET.get(REDIRECT_FIELD_NAME)
            or reverse(self.admin_index)
        }
        if user.is_authenticated:
            has_access = (
                user.has_perm(self.access_permission)
                if self.access_permission
                else user.is_staff
            )
            if has_access:
                return redirect(self.admin_index)
            params[SWITCH_ACCOUNT_PARAM] = "1"
        return redirect(f"{reverse('login')}?{urlencode(params)}")
