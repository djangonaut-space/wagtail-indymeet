from django.urls import include
from django.urls import path

from .two_factor_views import TwoFactorDisableView
from .two_factor_views import TwoFactorLoginView
from .two_factor_views import TwoFactorRecoverView
from .two_factor_views import TwoFactorRecoveryCodesView
from .two_factor_views import TwoFactorSetupView
from .two_factor_views import TwoFactorVerifyView
from .two_factor_views import TwoFactorView
from .views import ActivateAccountView
from .views import CustomPasswordResetView
from .views import DeleteAccountView
from .views import profile
from .views import ResendConfirmationEmailView
from .views import SignUpView
from .views import UpdateAvailabilityView
from .views import UpdateEmailSubscriptionView
from .views import UpdateTimezoneView
from .views import UpdateUserView

urlpatterns = [
    path(
        "login/",
        TwoFactorLoginView.as_view(),
        name="login",
    ),
    path(
        "login/verify/",
        TwoFactorVerifyView.as_view(),
        name="two_factor_verify",
    ),
    path(
        "password_reset/",
        CustomPasswordResetView.as_view(),
        name="password_reset",
    ),
    path("", include("django.contrib.auth.urls")),
    path("profile/", profile, name="profile"),
    path("profile/update/", UpdateUserView.as_view(), name="update_user"),
    path("signup/", SignUpView.as_view(), name="signup"),
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
    path("two-factor/", TwoFactorView.as_view(), name="two_factor"),
    path(
        "two-factor/setup/",
        TwoFactorSetupView.as_view(),
        name="two_factor_setup",
    ),
    path(
        "two-factor/recovery-codes/",
        TwoFactorRecoveryCodesView.as_view(),
        name="two_factor_recovery_codes",
    ),
    path(
        "two-factor/recover/<str:token>/",
        TwoFactorRecoverView.as_view(),
        name="two_factor_recover",
    ),
    path(
        "two-factor/disable/",
        TwoFactorDisableView.as_view(),
        name="two_factor_disable",
    ),
]
