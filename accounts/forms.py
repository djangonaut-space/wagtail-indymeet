from django import forms
from django.utils.translation import gettext_lazy as _

from wagtail.users.forms import UserEditForm, UserCreationForm

from accounts.models import CustomUser


class CustomUserEditForm(UserEditForm):
    pass

class CustomUserCreationForm(UserCreationForm):
    pass