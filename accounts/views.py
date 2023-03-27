# Create your views here.
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView

from .forms import CustomUserCreationForm
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


class SignUpView(CreateView): # pylint: disable=C0115
    form_class = CustomUserCreationForm
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"


@login_required(login_url='/accounts/login') #redirect when user is not logged in
def profile(request):
    return render(request, 'registration/profile.html')
