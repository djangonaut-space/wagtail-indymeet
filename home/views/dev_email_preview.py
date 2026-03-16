from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone


def preview_acceptance_reminder(request):
    class DummyMembership:
        acceptance_deadline = timezone.now() + timedelta(days=3)

    class DummySession:
        start_date = timezone.now()
        end_date = timezone.now() + timedelta(days=30)

    context = {
        "membership": DummyMembership(),
        "session": DummySession(),
    }

    return render(request, "email/acceptance_reminder/body.html", context)


def preview_session_accepted(request):
    class DummyMembership:
        acceptance_deadline = timezone.now() + timedelta(days=3)

    class DummySession:
        start_date = timezone.now()
        end_date = timezone.now() + timedelta(days=30)

    context = {
        "membership": DummyMembership(),
        "session": DummySession(),
    }

    return render(request, "email/session_accepted/body.html", context)
