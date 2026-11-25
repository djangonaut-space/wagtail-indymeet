from allauth.account import views as allauth_views
from allauth.account.decorators import reauthentication_required
from allauth.urls import build_provider_urlpatterns
from django.contrib.auth import views as auth_views
from django.urls import include
from django.urls import path

from .views import ActivateAccountView
from .views import CustomPasswordChangeView
from .views import CustomPasswordResetView
from .views import DeleteAccountView
from .views import lacks_password
from .views import profile
from .views import ResendConfirmationEmailView
from .views import SignUpView
from .views import UpdateAvailabilityView
from .views import UpdateEmailSubscriptionView
from .views import UpdateTimezoneView
from .views import UpdateUserView

# django-allauth handles login, two-factor authentication and GitHub sign-in.
# Its views are routed one by one rather than through ``allauth.urls`` because
# signup, email confirmation and password reset remain this project's own, and
# allauth's versions of those must not be reachable alongside them.
#
# allauth looks up some pages by its own URL names, so the project's signup,
# logout and password reset are also registered under the names it expects.
urlpatterns = [
    path("login/", allauth_views.login, name="login"),
    path("login/", allauth_views.login, name="account_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="account_logout"),
    path("inactive/", allauth_views.account_inactive, name="account_inactive"),
    path(
        "reauthenticate/",
        allauth_views.reauthenticate,
        name="account_reauthenticate",
    ),
    path(
        "reauthenticate/code/",
        allauth_views.request_reauthentication_code,
        name="account_request_reauthentication_code",
    ),
    path(
        "reauthenticate/code/confirm/",
        allauth_views.confirm_reauthentication_code,
        name="account_confirm_reauthentication_code",
    ),
    path("two-factor/", include("allauth.mfa.urls")),
    path("social/", include("allauth.socialaccount.urls")),
    *build_provider_urlpatterns(),
    path(
        "password_reset/",
        CustomPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password_reset/",
        CustomPasswordResetView.as_view(),
        name="account_reset_password",
    ),
    # Users without a password (GitHub signups) are sent on to set one, after
    # confirming it is them with a code sent to their email.
    path(
        "password_change/", CustomPasswordChangeView.as_view(), name="password_change"
    ),
    path(
        "password_change/",
        CustomPasswordChangeView.as_view(),
        name="account_change_password",
    ),
    path(
        "password/set/",
        reauthentication_required(allauth_views.password_set, enabled=lacks_password),
        name="account_set_password",
    ),
    path("", include("django.contrib.auth.urls")),
    path("profile/", profile, name="profile"),
    path("profile/update/", UpdateUserView.as_view(), name="update_user"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("signup/", SignUpView.as_view(), name="account_signup"),
    path(
        "activate/<uidb64>/<token>",
        ActivateAccountView.as_view(),
        name="activate_account",
    ),
    path(
        "resend_email_confirmation/",
        ResendConfirmationEmailView.as_view(),
        name="resend_email_confirmation",
    ),
    path(
        "email_subscriptions/",
        UpdateEmailSubscriptionView.as_view(),
        name="email_subscriptions",
    ),
    path(
        "availability/",
        UpdateAvailabilityView.as_view(),
        name="availability",
    ),
    path(
        "profile/timezone/",
        UpdateTimezoneView.as_view(),
        name="update_timezone",
    ),
    path(
        "delete/",
        DeleteAccountView.as_view(),
        name="delete_account",
    ),
]
