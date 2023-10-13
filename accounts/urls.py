from __future__ import annotations

from django.urls import include
from django.urls import path

from .views import ActivateAccountView
from .views import profile
from .views import SignUpView
from .views import unsubscribe

urlpatterns = [
    path("", include("django.contrib.auth.urls")),
    path("profile/", profile, name="profile"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path(
        "activate/<uidb64>/<token>",
        ActivateAccountView.as_view(),
        name="activate_account",
    ),
    path("unsubscribe/<user_id>/<token>", unsubscribe, name="unsubscribe"),
]
