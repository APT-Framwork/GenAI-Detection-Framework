from django.http import HttpResponse
from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import *
from django.contrib.auth.forms import UserCreationForm

# Create your views here.

def registerPage(request):
    if request.method == "POST":
        form = CreateUserForm(request.POST)
        if form.is_valid():
            form.save()
            user = form.cleaned_data["username"]
            messages.success(request, "Account was created for " + str(user))
            return redirect("authenticate-index")
        else:
            messages.error(request, "Account was not created !")
            return redirect("register-page")
    else:
        form = CreateUserForm()
        contexte = {
            "form": form,
        }
        return render(request, "register.html", contexte)

def authenticate_index(request):
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = authenticate_index_form(request.POST)
        # check whether it's valid:
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                # Redirect to a success page.
                return redirect('My_app-workspaces')
            else:
                messages.success(request, ("Wrong Password. Please try again"))
                # Return an 'invalid login' error message.
                return redirect('authenticate-index')


        # if a GET (or any other method) we'll create a blank form
    else:
        form = authenticate_index_form()

    contexte = {
        'form': form
    }
    return render(request, "index.html", contexte)

@login_required
def authenticate_welcome(request):
    session_data = request.session.items()
    contexte = {
        'session': session_data
    }
    return render(request, 'welcome.html', contexte)