from django.urls import path
from django.views.generic import TemplateView

from home.views.compare_availability import (
    compare_availability,
    compare_availability_grid,
)
from home.views.events import EventDetailView, EventListView, event_calendar
from home.views.membership_acceptance import accept_membership_view
from home.views.resources import resource_link
from home.views.sessions import SessionDetailView, SessionListView, UserSessionListView
from home.views.surveys import (
    CreateUserSurveyResponseFormView,
    EditUserSurveyResponseView,
    UserSurveyResponseView,
)
from home.views.teams import (
    DjangonautSurveyResponseView,
    TeamDetailView,
    team_availability_fragment,
)
from home.views.testimonials import (
    TestimonialCreateView,
    TestimonialDeleteView,
    TestimonialListView,
    TestimonialUpdateView,
)

urlpatterns = [
    path("calendar/", event_calendar, name="calendar"),
    path(
        "compare-availability/",
        compare_availability,
        name="compare_availability",
    ),
    path(
        "compare-availability/grid/",
        compare_availability_grid,
        name="compare_availability_grid",
    ),
    path("events/", EventListView.as_view(), name="event_list"),
    path(
        "events/<int:year>/<int:month>/<slug:slug>/",
        EventDetailView.as_view(),
        name="event_detail",
    ),
    path("my-sessions/", UserSessionListView.as_view(), name="user_sessions"),
    path("sessions/", SessionListView.as_view(), name="session_list"),
    path("sessions/<slug:slug>/", SessionDetailView.as_view(), name="session_detail"),
    path(
        "sessions/<slug:slug>/accept/",
        accept_membership_view,
        name="accept_membership",
    ),
    path(
        "sessions/<slug:session_slug>/teams/<int:pk>/",
        TeamDetailView.as_view(),
        name="team_detail",
    ),
    path(
        "teams/<int:pk>/availability/",
        team_availability_fragment,
        name="team_availability_fragment",
    ),
    path(
        "sessions/<slug:session_slug>/djangonauts/<int:user_id>/survey-response/",
        DjangonautSurveyResponseView.as_view(),
        name="djangonaut_survey_response",
    ),
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
    path("testimonials/", TestimonialListView.as_view(), name="testimonial_list"),
    path(
        "testimonials/create/",
        TestimonialCreateView.as_view(),
        name="testimonial_create",
    ),
    path(
        "testimonials/<slug:slug>/edit/",
        TestimonialUpdateView.as_view(),
        name="testimonial_edit",
    ),
    path(
        "testimonials/<slug:slug>/delete/",
        TestimonialDeleteView.as_view(),
        name="testimonial_delete",
    ),
]
