# Create your views here.
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.views import View
from django.views.generic.edit import CreateView

from .forms import CustomUserCreationForm
from .tokens import account_activation_token


User = get_user_model()


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
        user.profile.receiving_event_updates = form.cleaned_data[
            "receive_event_updates"
        ]
        user.profile.save(
            update_fields=[
                "accepted_coc",
                "receiving_newsletter",
                "receiving_event_updates",
            ]
        )
        invite_link = reverse(
            "activate_account",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": account_activation_token.make_token(user),
            },
        )
        message = (
            "To confirm your email address on djangonaut.space please visit the link: "
            + self.request.build_absolute_uri(invite_link)
        )
        send_mail(
            "Djangonaut Space Registration Confirmation",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return super().form_valid(form)


@login_required(login_url="/accounts/login")  # redirect when user is not logged in
def profile(request):
    return render(request, "registration/profile.html")


def unsubscribe(request, user_id, token):
    """
    User is immediately unsubscribed if user is found. Otherwise, they are
    redirected to the login page and unsubscribed as soon as they log in.
    """

    user = get_object_or_404(User, id=user_id, is_active=True)

    if (
        request.user.is_authenticated and request.user == user
    ) or user.profile.check_token(token):
        # unsubscribe them
        profile = user.profile
        if request.GET.get("events", None):
            email_type = "events"
            profile.receiving_event_updates = False
        else:
            email_type = "newsletters"
            profile.receiving_newsletter = False
        profile.save()

        return render(
            request, "registration/unsubscribed.html", {"email_type": email_type}
        )

    # Otherwise redirect to login page
    next_url = reverse(
        "unsubscribe",
        kwargs={
            "user_id": user_id,
            "token": token,
        },
    )
    return HttpResponseRedirect(f"{reverse('login')}?next={next_url}")
