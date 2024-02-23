from __future__ import annotations

from django.urls import path

from .views import (
    CreateUserSurveyResponseFormView,
    EventDetailView,
    EventListView,
    SessionDetailView,
    SessionListView,
    event_calendar,
)

urlpatterns = [
    path("calendar/", event_calendar, name="calendar"),
    path("events/", EventListView.as_view(), name="event_list"),
    path(
        "events/<int:year>/<int:month>/<slug:slug>/",
        EventDetailView.as_view(),
        name="event_detail",
    ),
    path("sessions/", SessionListView.as_view(), name="session_list"),
    path("sessions/<slug:slug>/", SessionDetailView.as_view(), name="session_detail"),
    path(
        "survey_response/create/<str:slug>/",
        CreateUserSurveyResponseFormView.as_view(),
        name="survey_response_create",
    ),
]
