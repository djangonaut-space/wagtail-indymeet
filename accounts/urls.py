from django.urls import include, path

from .views import SignUpView, profile

urlpatterns = [
    path("", include('django.contrib.auth.urls')),
    path("profile/", profile, name="profile" ),
    path("signup/", SignUpView.as_view(), name="signup"),
]