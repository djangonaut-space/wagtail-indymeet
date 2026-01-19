# Create your views here.
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, REDIRECT_FIELD_NAME
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import PasswordResetView
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.views import View
from django.views.generic.edit import CreateView
from django.views.generic.edit import FormView
from django.views.generic.edit import UpdateView

from home.email import send

from .forms import CustomUserChangeForm
from .forms import CustomUserCreationForm
from .forms import DeleteAccountForm
from .forms import EmailSubscriptionsChangeForm
from .forms import UserAvailabilityForm
from .models import UserAvailability
from .tasks import delete_user_account
from .tokens import account_activation_token

User = get_user_model()


class CustomPasswordResetView(PasswordResetView):
    html_email_template_name = "registration/html_password_reset_email.html"


class ActivateAccountView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and account_activation_token.check_token(user, token):
            user.profile.email_confirmed = True
            user.profile.save()
            login(request, user)
            return redirect("profile")
        else:
            # invalid link
            messages.error(request, "Your confirmation link is invalid.")
            return redirect("signup")


def send_user_confirmation_email(request, user):
    invite_link = reverse(
        "activate_account",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": account_activation_token.make_token(user),
        },
    )
    email_context = {
        "cta_link": request.build_absolute_uri(invite_link),
        "name": user.get_full_name(),
    }
    send(
        email_template="email_confirmation",
        recipient_list=[user.email],
        context=email_context,
    )


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "registration/signup.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class=form_class)
        if settings.LOAD_TESTING:
            form.fields.pop("captcha")
        return form

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.INFO,
            "Your registration was successful. Please check "
            "your email provided for a confirmation link.",
        )
        return self.request.POST.get(
            REDIRECT_FIELD_NAME,
            self.request.GET.get(REDIRECT_FIELD_NAME, reverse("profile")),
        )

    def form_valid(self, form):
        """sends a link for a user to activate their account after signup"""

        self.object = form.save()
        user = self.object
        user.profile.accepted_coc = form.cleaned_data["accepted_coc"]
        user.profile.receiving_newsletter = form.cleaned_data["receive_newsletter"]
        user.profile.receiving_program_updates = form.cleaned_data[
            "receive_program_updates"
        ]
        user.profile.receiving_event_updates = form.cleaned_data[
            "receive_event_updates"
        ]
        if settings.LOAD_TESTING:
            user.profile.email_confirmed = True
            user.profile.save(
                update_fields=[
                    "email_confirmed",
                    "accepted_coc",
                    "receiving_newsletter",
                    "receiving_program_updates",
                    "receiving_event_updates",
                ]
            )
        else:
            user.profile.save(
                update_fields=[
                    "accepted_coc",
                    "receiving_newsletter",
                    "receiving_program_updates",
                    "receiving_event_updates",
                ]
            )
            send_user_confirmation_email(self.request, user)
        return super().form_valid(form)


@login_required(login_url="/accounts/login")
def profile(request):
    context = {
        "user_responses": request.user.usersurveyresponse_set.select_related("survey")
    }
    return render(request, "registration/profile.html", context)


class ResendConfirmationEmailView(LoginRequiredMixin, View):
    def post(self, request):
        user = request.user
        send_user_confirmation_email(request, user)
        messages.add_message(
            request,
            messages.SUCCESS,
            f"A verification email has been sent to {user.email}",
        )
        return redirect("profile")


class UpdateUserView(LoginRequiredMixin, UpdateView):
    form_class = CustomUserChangeForm
    template_name = "registration/update_user.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        initial = super().get_initial()
        initial["receive_program_updates"] = (
            self.request.user.profile.receiving_program_updates
        )
        initial["receive_event_updates"] = (
            self.request.user.profile.receiving_event_updates
        )
        initial["receive_newsletter"] = self.request.user.profile.receiving_newsletter
        return initial

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.INFO,
            "Your profile information has been updated successfully.",
        )
        return reverse("profile")

    def form_valid(self, form):
        self.object = form.save()
        user = self.object
        user.profile.receiving_newsletter = form.cleaned_data["receive_newsletter"]
        user.profile.receiving_program_updates = form.cleaned_data[
            "receive_program_updates"
        ]
        user.profile.receiving_event_updates = form.cleaned_data[
            "receive_event_updates"
        ]
        user.profile.save(
            update_fields=[
                "receiving_newsletter",
                "receiving_program_updates",
                "receiving_event_updates",
            ]
        )
        """sends a link for a user to activate their account after changing their email"""
        if "email" in form.changed_data:
            user.profile.email_confirmed = False
            user.profile.save()
            send_user_confirmation_email(self.request, user)
        return super().form_valid(form)


class UpdateEmailSubscriptionView(LoginRequiredMixin, UpdateView):
    form_class = EmailSubscriptionsChangeForm
    template_name = "registration/update_email_subscriptions.html"

    def get_object(self, queryset=None):
        return self.request.user.profile

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.INFO,
            "Your profile information has been updated successfully.",
        )
        return reverse("profile")


class UpdateAvailabilityView(LoginRequiredMixin, UpdateView):
    """View for updating user's weekly availability."""

    form_class = UserAvailabilityForm
    template_name = "registration/update_availability.html"

    def get_object(self, queryset=None):
        """Get or create the UserAvailability object for the current user."""
        availability, created = UserAvailability.objects.get_or_create(
            user=self.request.user
        )
        return availability

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.SUCCESS,
            "Your availability has been updated successfully.",
        )
        return reverse("profile")


class DeleteAccountView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """Display account deletion confirmation page and process deletion requests."""

    template_name = "registration/delete_account_confirmation.html"
    form_class = DeleteAccountForm
    success_url = reverse_lazy("login")

    def test_func(self):
        """Check that the user is not a staff member."""
        return not self.request.user.is_staff

    def handle_no_permission(self):
        """Redirect to profile with error message when staff tries to delete account."""
        # If user is not authenticated, let LoginRequiredMixin handle it
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        # User is authenticated but is staff
        messages.error(
            self.request,
            "Staff accounts cannot be deleted. Please contact an administrator "
            "if you need to remove your account.",
        )
        return redirect("profile")

    def get_form_kwargs(self):
        """Pass the current user to the form for validation."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Add deletion statistics to context."""
        return super().get_context_data(
            **kwargs,
            session_memberships_count=self.request.user.session_memberships.count(),
            survey_responses_count=self.request.user.usersurveyresponse_set.count(),
        )

    def form_valid(self, form):
        """Process account deletion and enqueue background task."""
        user_id = self.request.user.id

        delete_user_account.enqueue(user_id=user_id)

        logout(self.request)

        messages.info(
            self.request,
            "Your account deletion has been initiated. You will receive a "
            "confirmation email once the process is complete. Thank you for "
            "being part of Djangonaut Space.",
        )
        return redirect("login")
