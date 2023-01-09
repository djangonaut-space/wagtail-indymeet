from django.urls import include, path

from .views import SignUpView, profile, ActivateAccountView

urlpatterns = [
    path("", include('django.contrib.auth.urls')),
    path("profile/", profile, name="profile" ),
    path("signup/", SignUpView.as_view(), name="signup"),
    path('activate/<uidb64>/<token>', ActivateAccountView.as_view(), name='activate_account'),
]