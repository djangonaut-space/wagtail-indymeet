# Create your views here.
from django.conf import settings
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.urls import reverse
from django.utils.encoding import force_str, force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic.edit import CreateView
from django.views import View


User = get_user_model()

from .forms import CustomUserCreationForm
from .tokens import account_activation_token

class ActivateAccountView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and account_activation_token.check_token(user, token):
            user.profile.email_confirmed = True
            user.save()
            login(request, user)
            return redirect('profile')
        else:
            # invalid link
            messages.add_message(request, messages.ERROR, 'Your confirmation link is invalid.')
            return redirect('signup')



class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "registration/signup.html"

    def get_success_url(self):
        messages.add_message(
            self.request,
            messages.INFO,
            'Your registration was successful. Please check your email provided for a confirmation link.'
        )
        return reverse('signup')


    def form_valid(self, form):
        """sends a link for a user to activate their account after signup"""

        self.object = form.save()
        user = self.object
        invite_link = reverse(
            "activate_account",

            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": account_activation_token.make_token(user),
            },
        )
        registration_url =  f"{invite_link}"
        send_mail(
            'Djangonaut Space Registration Confirmation',
            f'The invitation link is: {registration_url}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return super().form_valid(form)


@login_required(login_url='/accounts/login') #redirect when user is not logged in
def profile(request):
    return render(request, 'registration/profile.html')
