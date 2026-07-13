from django import forms

from availability.models import UserAvailability


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
