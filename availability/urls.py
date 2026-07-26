from django.urls import path

from availability import views

urlpatterns = [
    path("availability/", views.UpdateAvailabilityView.as_view(), name="availability"),
    path(
        "availability/calendar/google/connect/",
        views.google_calendar_connect,
        name="google_calendar_connect",
    ),
    path(
        "availability/calendar/google/callback/",
        views.google_calendar_callback,
        name="google_calendar_callback",
    ),
    path(
        "availability/calendar/google/webhook/",
        views.google_calendar_webhook,
        name="google_calendar_webhook",
    ),
    path(
        "availability/calendar/<int:pk>/disconnect/",
        views.calendar_disconnect,
        name="calendar_disconnect",
    ),
    path(
        "availability/calendar/import/",
        views.calendar_import,
        name="calendar_import",
    ),
]
