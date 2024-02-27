from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import include
from django.urls import path

from .views import ActivateAccountView
from .views import profile
from .views import SignUpView
from .views import unsubscribe

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(redirect_field_name="next_page"),
        name="login",
    ),
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
