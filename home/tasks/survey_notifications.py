from accounts.models import UserAvailability
from home import email
from home.models import UserSurveyResponse, Session


def _send_application_notification(
    email_template: str, survey_response: UserSurveyResponse, session: Session
):
    """Send an email to the user about the application."""
    availability, _ = UserAvailability.objects.get_or_create(user=survey_response.user)
    context = {
        "user": survey_response.user,
        "name": survey_response.user.first_name or survey_response.user.email,
        "availability": availability,
        "response": survey_response,
        "session": session,
        "cta_link": survey_response.get_full_url(),
    }
    email.send(
        email_template=email_template,
        recipient_list=[survey_response.user.email],
        context=context,
    )


def send_application_created_notification(
    survey_response: UserSurveyResponse, session: Session
):
    """Send an email to the user about the created application."""
    _send_application_notification("application_created", survey_response, session)


def send_application_updated_notification(
    survey_response: UserSurveyResponse, session: Session
):
    """Send an email to the user about the updated application."""
    _send_application_notification("application_updated", survey_response, session)
