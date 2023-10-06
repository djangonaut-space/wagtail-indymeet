from django.urls import path

from .views import event_calendar, EventDetailView, EventListView

urlpatterns = [
    path('calendar/', event_calendar, name="calendar"),
    path('event-list/', EventListView.as_view(), name="event_list"),
    path('events/<int:year>/<int:month>/<slug:slug>/', EventDetailView.as_view(), name="event_detail"),
]