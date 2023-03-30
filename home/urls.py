from django.urls import path

from .views import event_calendar, EventDetailView

urlpatterns = [
    path('calendar/', event_calendar, name="calendar"),
    path('events/<pk>/', EventDetailView.as_view(), name="event_detail"),
]