from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import include
from django.urls import path

from .views import ActivateAccountView
from .views import CustomPasswordResetView
from .views import profile
from .views import ResendConfirmationEmailView
from .views import SignUpView
from .views import UpdateEmailSubscriptionView
from .views import UpdateUserView

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(redirect_field_name="next_page"),
        name="login",
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
]
