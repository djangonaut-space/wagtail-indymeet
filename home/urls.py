from django.urls import path
from django.views.generic import TemplateView

from .views import CreateUserSurveyResponseFormView
from .views import resource_link
from .views import event_calendar
from .views import EventDetailView
from .views import EventListView
from .views import SessionDetailView
from .views import SessionListView
from .views import UserSurveyResponseView

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
    path(
        "survey_response/<int:pk>/",
        UserSurveyResponseView.as_view(),
        name="user_survey_response",
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
