from __future__ import annotations

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox
from django import forms
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.forms import UserCreationForm

from .models import CustomUser


class CustomUserCreationForm(UserCreationForm):
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())
    email_consent = forms.BooleanField(
        help_text="Required: Please check this to consent to receiving "
        "administrative emails like: email verification, password reset etc.",
        label="Email Consent*",
    )
    receive_newsletter = forms.BooleanField(
        required=False,
        help_text="Optional: Please check this to opt-in for receiving "
        "general updates about community and events. You can "
        "opt-out on your profile page at anytime.",
    )
    receive_event_updates = forms.BooleanField(
        required=False,
        help_text="Optional: Please check this to opt-in for receiving "
        "emails to events you register to. You can opt-out on "
        "your profile page at anytime.",
    )
    accepted_coc = forms.BooleanField(
        required=True,
        label="Accept CoC*",
        help_text="Required: please read over and accept "
        "<a href='https://github.com/djangonaut-space/pilot-program/blob/main/CODE_OF_CONDUCT.md'>"  # noqa B950
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
            "receive_newsletter",
            "receive_event_updates",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
        )
