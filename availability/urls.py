from django.urls import path

from availability import views

urlpatterns = [
    path("availability/", views.UpdateAvailabilityView.as_view(), name="availability"),
]
