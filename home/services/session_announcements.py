"""Seeding a session with its weekly Discord announcements."""

from django.db import transaction

from home.announcements import WEEKLY_ANNOUNCEMENTS
from home.models import Announcement, Session


def _organizer_names(session: Session) -> str:
    """This session's organizers, as a readable list for the welcome message.

    Falls back to a placeholder when nobody is recorded or nobody has a name
    set, so the gap shows up during approval rather than posting as an empty
    sentence. Emails are never used — this goes out in a public channel.
    """
    names = [
        name
        for membership in session.session_memberships.organizers().select_related(
            "user"
        )
        if (name := membership.user.get_full_name())
    ]
    if not names:
        return "<session organizer names>"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def build_template_context(session: Session) -> dict[str, str]:
    """The session-derived values an announcement template can interpolate.

    Only templates that need approval use these, so a missing session field
    can never silently degrade an announcement that posts automatically.
    """
    return {
        "organizers": _organizer_names(session),
        "feedback_form_url": session.feedback_form_url or "<feedback form link>",
        "session_name": session.short_name,
    }


def generate_announcements(session: Session) -> int:
    """Create any weekly announcements this session is still missing.

    Additive only. Weeks that already have an announcement are left exactly as
    the organizers left them, so rerunning the Discord setup action never
    reverts an edited message, an approval, or a post.

    Args:
        session: The session to seed.

    Returns:
        The number of announcements created.
    """
    existing_weeks = set(
        session.announcements.values_list("week_number", flat=True),
    )
    context = build_template_context(session)
    announcements = []
    for template in WEEKLY_ANNOUNCEMENTS:
        if template.week_number in existing_weeks:
            continue
        post_date = session.week_start_date(template.week_number)
        announcements.append(
            Announcement(
                session=session,
                post_date=post_date,
                week_number=template.week_number,
                message=template.render(context),
                approval_note=template.approval_note,
                needs_approval=template.needs_approval,
            )
        )

    with transaction.atomic():
        Announcement.objects.bulk_create(announcements)
    return len(announcements)
