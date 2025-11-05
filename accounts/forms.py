from django import forms
from django.contrib.auth.forms import UserCreationForm
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox

from .models import CustomUser
from .models import UserAvailability
from .models import UserProfile


class BaseCustomUserForm(forms.ModelForm):
    receive_newsletter = forms.BooleanField(
        required=False,
        help_text="Optional: Please check this to opt-in for receiving "
        "a newsletter containing general updates about Djangonaut Space. "
        "This newsletter does not yet exist. You can opt-out on your profile "
        "page at anytime.",
    )
    receive_event_updates = forms.BooleanField(
        required=False,
        help_text="Optional: Please check this to opt-in for receiving "
        "emails about upcoming community events. You can opt-out on "
        "your profile page at anytime.",
    )
    receive_program_updates = forms.BooleanField(
        required=False,
        help_text="Optional: Please check this to opt-in for receiving "
        "emails about upcoming program sessions. You can opt-out on "
        "your profile page at anytime.",
    )


class CustomUserCreationForm(BaseCustomUserForm, UserCreationForm):
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())
    email_consent = forms.BooleanField(
        help_text="Required: Please check this to consent to receiving "
        "administrative emails like: email verification, password reset etc.",
        label="Email Consent*",
    )
    accepted_coc = forms.BooleanField(
        required=True,
        label="Accept CoC*",
        help_text="Required: please read over and accept "
        "<a href='https://github.com/djangonaut-space/program/blob/main/CODE_OF_CONDUCT.md'>"  # noqa B950
        "the CoC"
        "</a>",
    )

    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "password1",
            "password2",
            "email_consent",
            "accepted_coc",
            "receive_program_updates",
            "receive_event_updates",
            "receive_newsletter",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class CustomUserChangeForm(BaseCustomUserForm):
    class Meta(BaseCustomUserForm):
        model = CustomUser
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "receive_program_updates",
            "receive_event_updates",
            "receive_newsletter",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        user = kwargs["instance"]
        if user.profile.email_confirmed:
            help_text = (
                "<p class='text-amber-600'>If you update your email"
                " you will need to reconfirm your email address.</p>"
            )
            self.fields["email"].help_text = help_text
        else:
            help_text = "<p class='text-amber-600'>You have not confirmed your email address.</p>"
            self.fields["email"].help_text = help_text


class EmailSubscriptionsChangeForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = (
            "receiving_newsletter",
            "receiving_event_updates",
            "receiving_program_updates",
        )
        labels = {
            "receiving_newsletter": "Subscribe to newsletter",
            "receiving_event_updates": "Subscribe to event updates",
            "receiving_program_updates": "Subscribe to program updates ",
        }
        help_texts = {
            "receiving_newsletter": "Please check this to opt-in for receiving our newsletter."
            "You can opt-out on your profile page at anytime.",
            "receiving_event_updates": "Please check this to opt-in for receiving emails about "
            "upcoming events. You can opt-out on your profile page at anytime.",
            "receiving_program_updates": "Please check this to opt-in for receiving emails about "
            "upcoming program sessions. You can opt-out on your profile page at anytime.",
        }


class UserAvailabilityForm(forms.ModelForm):
    """
    Form for updating user availability.

    The actual slot selection happens via JavaScript on the frontend.
    This form just handles the JSON data submission.
    """

    slots = forms.JSONField(
        required=False,
        widget=forms.HiddenInput(),
        help_text="Your weekly availability slots (managed via the calendar interface)",
    )

    class Meta:
        model = UserAvailability
        fields = ("slots",)
