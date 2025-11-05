from django.urls import path
from django.views.generic import TemplateView

from home.views.events import EventDetailView, EventListView, event_calendar
from home.views.resources import resource_link
from home.views.sessions import SessionDetailView, SessionListView
from home.views.surveys import (
    CreateUserSurveyResponseFormView,
    EditUserSurveyResponseView,
    UserSurveyResponseView,
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
        "survey/<str:slug>/response/create/",
        CreateUserSurveyResponseFormView.as_view(),
        name="survey_response_create",
    ),
    path(
        "survey/<str:slug>/response/",
        UserSurveyResponseView.as_view(),
        name="user_survey_response",
    ),
    path(
        "survey/<str:slug>/response/edit/",
        EditUserSurveyResponseView.as_view(),
        name="edit_user_survey_response",
    ),
    path("resource/<path:path>", resource_link, name="resource_link"),
    path(
        "contribute/opportunities/",
        TemplateView.as_view(
            template_name="home/opportunities.html", extra_context={"blog_page": True}
        ),
        name="opportunities",
    ),
]
