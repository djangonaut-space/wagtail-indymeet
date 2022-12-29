from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required(login_url='/accounts/login') #redirect when user is not logged in
def Profile(request):
    return render(request, 'registration/profile.html')