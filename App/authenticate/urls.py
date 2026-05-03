from django.urls import path
from .views import *

urlpatterns = [
    path("", authenticate_index, name="authenticate-index"),
    path("welcome/", authenticate_welcome, name="authenticate-welcome"),
    path("register/", registerPage, name="register-page"),
]