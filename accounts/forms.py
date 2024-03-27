from __future__ import annotations

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import CustomUser


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
            self.fields["email"].help_text = (
                "<p class='text-amber-600'>If you update your email you will need to reconfirm your email address.</p>"
            )
        else:
            self.fields["email"].help_text = (
                "<p class='text-amber-600'>You have not confirmed your email address.</p>"
            )
