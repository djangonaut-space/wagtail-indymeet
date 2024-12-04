# Create your views here.
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordResetView
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.views import View
from django.views.generic.edit import CreateView
from django.views.generic.edit import UpdateView

from .forms import CustomUserChangeForm
from .forms import CustomUserCreationForm
from .forms import EmailSubscriptionsChangeForm
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
            messages.add_message(
                request, messages.ERROR, "Your confirmation link is invalid."
            )
            return redirect("signup")


def send_user_confirmation_email(request, user):
    invite_link = reverse(
        "activate_account",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": account_activation_token.make_token(user),
        },
    )
    unsubscribe_link = reverse("email_subscriptions")
    email_dict = {
        "cta_link": request.build_absolute_uri(invite_link),
        "name": user.get_full_name(),
        "unsubscribe_link": request.build_absolute_uri(unsubscribe_link),
    }
    send_mail(
        "Djangonaut Space Email Confirmation",
        render_to_string("emails/email_confirmation.txt", email_dict),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=render_to_string("emails/email_confirmation.html", email_dict),
        fail_silently=False,
    )


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "registration/signup.html"

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.INFO,
            "Your registration was successful. Please check "
            "your email provided for a confirmation link.",
        )
        return reverse("signup")

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
    return render(request, "registration/profile.html")


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
