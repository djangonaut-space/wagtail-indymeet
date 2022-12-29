from django.urls import include, path
from accounts.views import Profile

urlpatterns = [
    path("", include('django.contrib.auth.urls')),
    path("profile/", Profile, name="profile" )
]