from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class authenticate_index_form(forms.Form):
    username = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                                                      {
                                                          'placeholder': 'Username',
                                                          'class': 'form-control',
                                                      }
                               ))
    password = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.PasswordInput(attrs={
                                   'placeholder': 'Password',
                                   'class': 'form-control',
                                   }
                                ))

class CreateUserForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super(CreateUserForm, self).__init__(*args, **kwargs)

        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'

        self.fields['username'].widget.attrs['placeholder'] = 'username'
        self.fields['password1'].widget.attrs['placeholder'] = 'password'
        self.fields['password2'].widget.attrs['placeholder'] = 'confirm password'