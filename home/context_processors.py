from datetime import timedelta

from django.utils import timezone

from accounts.models import UserAvailability
from home.models import Session


def alert_about_status(request):
    """
    Include information about the user's availability.

    It is imperative that users add their availability in addition
    to submitting a survey. This notice will be difficult to miss.
    """
    context = {}
    if request.user.is_authenticated:
        active_app_session = Session.objects.with_applications(
            request.user
        ).get_accepting_applications()
        if active_app_session:
            availability = UserAvailability.objects.filter(user=request.user).first()
            slots_count = len(availability.slots) if availability else 0
            if not slots_count:
                context["user_needs_to_set_availability"] = True
            elif request.user.availability.updated_at < timezone.now() - timedelta(
                days=30
            ):
                context["user_needs_to_update_availability"] = True
    return context
