from django import forms

class My_app_addworkspace(forms.Form):
    workspace_name = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Workspace name',
                                   'class': 'input',
                                   'style': "width: 30vw"
                               }
                               ))
#-----------------------------------------------------------------------------------------------------------------------
class Modify_workspace(forms.Form):
    domain_name = forms.CharField(required=False,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Domain name',
                                   'class': 'input',
                                   'style': "width: 30vw"
                               }
                               ))

    domain_user = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Domain user',
                                      'class': 'input',
                                      'style': "width: 30vw"
                                  }
                                  ))

    user_password = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.PasswordInput(attrs=
                                  {
                                      'placeholder': 'user password',
                                      'class': 'input',
                                      'style': "width: 30vw"
                                  }
                                  ))

    workspace_id = forms.CharField(required=True,
                                    max_length=100,
                                    widget=forms.HiddenInput(attrs=
                                    {

                                        'class': 'input',
                                        'style': "width: 30vw"
                                    }
                                    ))







#-----------------------------------------------------------------------------------------------------------------------

class Network_scan_form(forms.Form):
    network_scan_name = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Scan name',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))
    network_scan_ip = forms.CharField(required=True,
                                        max_length=100,
                                        widget=forms.TextInput(attrs=
                                        {
                                            'placeholder': 'ip',
                                            'class': 'input',
                                            'style': 'width: 30vw',
                                        }
                                        ))
    network_scan_ports= forms.CharField(required=False,
                                        max_length=100,
                                        widget=forms.TextInput(attrs=
                                        {
                                            'placeholder': 'Ports',
                                            'class': 'input',
                                            'style': 'width: 30vw',
                                        }
                                        ))

    CHOICES = [
        ('full_open_scan', 'Full open scan'),
        ('helf_open_scan', 'Half open scan'),
        ('xmas_scan', 'XMAS Scan'),
        ('udp_scan', 'UDP Scan'),
        ('ack_scan', 'ACK Scan'),

    ]
    network_scan_type = forms.ChoiceField(choices=CHOICES)

    service_version = forms.BooleanField(required=False,
                                         widget=forms.CheckboxInput(attrs=
                                                                    {
                                                                        'id': 'service_version_checkbox',
                                                                     }))
    os_discovery = forms.BooleanField(required=False,
                                         widget=forms.CheckboxInput(attrs=
                                         {
                                             'id': 'os_discovery_checkbox',
                                         }))

    # Verifier que il ne y'a pas de lettre dans le champ

# ----------------------------------------------------------------------------------------------------------------------

class Vuln_scan_form(forms.Form):
    vuln_scan_name = forms.CharField(required=True,
                                        max_length=100,
                                        widget=forms.TextInput(attrs=
                                        {
                                            'placeholder': 'Scan name',
                                            'class': 'input',
                                            'style': 'width: 30vw',
                                        }
                                        ))


    ip_address = forms.ChoiceField(choices=(), required=False)

    ip_address2 = forms.CharField(required=False,
                                        max_length=100,
                                        widget=forms.TextInput(attrs=
                                        {
                                            'placeholder': 'IP address',
                                            'class': 'input',
                                            'style': 'width: 30vw',
                                        }
                                        )) #
    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=
                                                                             {
                                                                                 "onchange": "toggleInputs()",
                                                                             }))

    def clean(self): #
        cleaned_data = super().clean()
        ip_address = cleaned_data.get('ip_address')
        ip_address2 = cleaned_data.get('ip_address2')

        if not ip_address and not ip_address2:
            raise forms.ValidationError("At least one field must be filled.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Vuln_scan_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['ip_address'].choices = choices

#-----------------------------------------------------------------------------------------------------------------------
class Ldap_enum_form(forms.Form):
    ldap_enum_name = forms.CharField(required=True,
                                        max_length=100,
                                        widget=forms.TextInput(attrs=
                                        {
                                            'placeholder': 'Name',
                                            'class': 'input',
                                            'style': 'width: 30vw',
                                        }
                                        ))

    domain_name = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Domain name',
                                   'class': 'input',
                                   'style': 'width: 30vw',
                               }
                               ))

    ip_address = forms.ChoiceField(choices=(), required=False)

    username = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'User',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))
    password = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.PasswordInput(attrs=
                                     {
                                         'placeholder': 'Password',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))

    ip_address2 = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'IP address',
                                      'class': 'input',
                                      'style': 'width: 30vw',
                                  }
                                  ))  #
    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        ip_address = cleaned_data.get('ip_address')
        ip_address2 = cleaned_data.get('ip_address2')

        if not ip_address and not ip_address2:
            raise forms.ValidationError("At least one field must be filled.")

        return cleaned_data



    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Ldap_enum_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['ip_address'].choices = choices

#-----------------------------------------------------------------------------------------------------------------------

class Smb_enum_form(forms.Form):
    smb_enum_name = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Name',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))
    ip_address = forms.ChoiceField(choices=(), required=False)

    ip_address2 = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'IP address',
                                      'class': 'input',
                                      'style': 'width: 30vw',
                                  }
                                  ))  #
    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()",}))

    def clean(self):  #
        cleaned_data = super().clean()
        ip_address = cleaned_data.get('ip_address')
        ip_address2 = cleaned_data.get('ip_address2')

        if not ip_address and not ip_address2:
            raise forms.ValidationError("At least one field must be filled.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Smb_enum_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['ip_address'].choices = choices


#-----------------------------------------------------------------------------------------------------------------------

class Port_listener_form(forms.Form):
    port_listener_name = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Name',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))

    payload = forms.ChoiceField(choices=(), required=True)

    port = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Name',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Port_listener_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['payload'].choices = choices


#-----------------------------------------------------------------------------------------------------------------------

class Password_cracking_form(forms.Form):
    password_cracking_name = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Name',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))

    wordlist_path = forms.CharField(required=True,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Wordlist path',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))

    hash_value = forms.CharField(required=False,
                                     max_length=100,
                                     widget=forms.TextInput(attrs=
                                     {
                                         'placeholder': 'Hash value',
                                         'class': 'input',
                                         'style': 'width: 30vw',
                                     }
                                     ))

    hash_type = forms.ChoiceField(choices=[("nt", "nt"), ("lm", "lm")], required=False)

    hash_choices = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        hash_value = cleaned_data.get('hash_value')
        hash_type = cleaned_data.get('hash_type')
        hash_choices = cleaned_data.get('hash_choices')

        if not hash_value and not hash_choices:
            raise forms.ValidationError("At least one field must be filled.")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Password_cracking_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['hash_choices'].choices = choices

#-----------------------------------------------------------------------------------------------------------------------

class Exploitation_form(forms.Form):
    imported_vuln = forms.ChoiceField(choices=(), required=True)

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Exploitation_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['imported_vuln'].choices = choices

#-----------------------------------------------------------------------------------------------------------------------

class Post_exp_form(forms.Form):
    activity_name = forms.CharField(required=True,
                                        max_length=100,
                                        widget=forms.TextInput(attrs=
                                        {
                                            'placeholder': 'Activity name',
                                            'class': 'input',
                                            'style': 'width: 30vw',
                                        }
                                        ))

    def __init__(self, *args, **kwargs):
        dynamic_fields = kwargs.pop('dynamic_fields', {})
        super(Post_exp_form, self).__init__(*args, **kwargs)
        for name, field in dynamic_fields.items():
            self.fields[name] = field


#-----------------------------------------------------------------------------------------------------------------------

class Pth_form(forms.Form):
    pth_name = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Activity name',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    username = forms.CharField(required=False,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Username',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    hash_value = forms.CharField(required=False,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Hash value',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    dc_checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs2()"}))

    domain = forms.CharField(required=False,
                                 max_length=100,
                                 widget=forms.TextInput(attrs=
                                 {
                                     'placeholder': 'Domain',
                                     'class': 'input',
                                     'style': "width: 20vw",
                                 }
                                 ))

    hash_choices = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))




    def clean(self):  #
        cleaned_data = super().clean()
        hash_value = cleaned_data.get('hash_value')
        username = cleaned_data.get('username')
        dc_checkbox = cleaned_data.get('dc_checkbox')
        domain = cleaned_data.get("domain")
        hash_choices = cleaned_data.get("hash_choices")

        if not hash_value and not hash_choices:
            raise forms.ValidationError("At least one field must be filled.")
        else:
            if hash_value:
                if dc_checkbox == True:
                    if not username or not hash_value or not domain:
                        raise forms.ValidationError("At least one field must be filled.")
                else:
                    if not username or not hash_value:
                        raise forms.ValidationError("At least one field must be filled.")


    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', None)
        super(Pth_form, self).__init__(*args, **kwargs)
        if choices:
            self.fields['hash_choices'].choices = choices




#-----------------------------------------------------------------------------------------------------------------------

class Dcsync_form(forms.Form):
    dcsync_name = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Activity name',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    ip_address = forms.CharField(required=False,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'DC ip address',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    domain = forms.CharField(required=False,
                                 max_length=100,
                                 widget=forms.TextInput(attrs=
                                 {
                                     'placeholder': 'domain name',
                                     'class': 'input',
                                     'style': "width: 20vw",
                                 }
                                 ))

    username = forms.CharField(required=False,
                             max_length=100,
                             widget=forms.TextInput(attrs=
                             {
                                 'placeholder': 'domain name',
                                 'class': 'input',
                                 'style': "width: 20vw",
                             }
                             ))

    password = forms.CharField(required=False,
                               max_length=100,
                               widget=forms.PasswordInput(attrs=
                               {
                                   'placeholder': 'Password',
                                   'class': 'input',
                                   'style': 'width: 20vw',
                               }
                               ))

    domain_controllers = forms.ChoiceField(choices=(), required=False)
    credentials = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        ip_address = cleaned_data.get('ip_address')
        domain = cleaned_data.get('domain')
        username = cleaned_data.get('username')
        password = cleaned_data.get("password")
        domain_controllers = cleaned_data.get("domain_controllers")
        credentials = cleaned_data.get("credentials")


        if not (ip_address and domain and username and password) and not (domain_controllers and credentials):
            raise forms.ValidationError("At least one field must be filled.")



    #def __init__(self, *args, **kwargs):
        #choices = kwargs.pop('choices', None)
        #choicess = kwargs.pop('choicess', None)
        #super(Dcsync_form, self).__init__(*args, **kwargs)
        #if choices:
            #self.fields['domain_controllers'].choices = choices


#-----------------------------------------------------------------------------------------------------------------------

class Golden_ticket_form(forms.Form):
    golden_ticket_name = forms.CharField(required=True,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Activity name',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    hash_krbtgt = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Hash krbtgt',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    domain = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Domain name',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    domain_sid = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Domain sid',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    spoofed_username = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Spoofed username',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    hash_krbtgt_choice = forms.ChoiceField(choices=(), required=False)
    spoofed_username_choice = forms.ChoiceField(choices=(), required=False)
    domain_sid_choice = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        hash_krbtgt = cleaned_data.get('hash_krbtgt')
        domain = cleaned_data.get('domain')
        domain_sid = cleaned_data.get('domain_sid')
        spoofed_username = cleaned_data.get("spoofed_username")
        hash_krbtgt_choice = cleaned_data.get("hash_krbtgt_choice")
        spoofed_username_choice = cleaned_data.get("spoofed_username_choice")
        domain_sid_choice = cleaned_data.get("domain_sid_choice")

        if not (hash_krbtgt and domain and domain_sid and spoofed_username) and not (domain and domain_sid_choice and hash_krbtgt_choice and spoofed_username_choice):
            print(hash_krbtgt_choice)
            print(spoofed_username_choice)
            print(domain_sid_choice)
            print(domain)
            raise forms.ValidationError("At least one field must be filled.")






#-----------------------------------------------------------------------------------------------------------------------

class Ptt_form(forms.Form):
    ptt_name = forms.CharField(required=True,
                                         max_length=100,
                                         widget=forms.TextInput(attrs=
                                         {
                                             'placeholder': 'Activity name',
                                             'class': 'input',
                                             'style': "width: 20vw",
                                         }
                                         ))

    ip_address = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Target ip address',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    ticket_path = forms.CharField(required=False,
                                 max_length=100,
                                 widget=forms.TextInput(attrs=
                                 {
                                     'placeholder': 'Ticket path',
                                     'class': 'input',
                                     'style': "width: 20vw",
                                 }
                                 ))

    ticket_path_choice = forms.ChoiceField(choices=(), required=False)
    ip_address_choice = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        ticket_path = cleaned_data.get('ticket_path')
        ip_address = cleaned_data.get('ip_address')
        ticket_path_choice = cleaned_data.get('ticket_path_choice')
        ip_address_choice = cleaned_data.get('ip_address_choice')
        checkbox = cleaned_data.get("checkbox")


        if not (ticket_path and ip_address) and not (ticket_path_choice and ip_address_choice):

            raise forms.ValidationError("At least one field must be filled.")


# ----------------------------------------------------------------------------------------------------------------------

class Kerberoasting_form(forms.Form):
    kerberoasting_name = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Activity name',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    domain_controler_ip = forms.CharField(required=False,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Domain controler ip',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    domain_name = forms.CharField(required=True,
                                          max_length=100,
                                          widget=forms.TextInput(attrs=
                                          {
                                              'placeholder': 'Domain name',
                                              'class': 'input',
                                              'style': "width: 20vw",
                                          }
                                          ))


    username = forms.CharField(required=True,
                                          max_length=100,
                                          widget=forms.TextInput(attrs=
                                          {
                                              'placeholder': 'Domain user',
                                              'class': 'input',
                                              'style': "width: 20vw",
                                          }
                                          ))

    user_password = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.PasswordInput(attrs=
                               {
                                   'placeholder': 'Password',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

    domain_controllers = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        domain_controler_ip = cleaned_data.get('domain_controler_ip')
        domain_name = cleaned_data.get('domain_name')
        username = cleaned_data.get('username')
        user_password = cleaned_data.get("user_password")
        domain_controllers = cleaned_data.get("domain_controllers")


        if not (domain_controler_ip and domain_name and username and user_password) and not (domain_controllers and domain_name and username and user_password):
            raise forms.ValidationError("At least one field must be filled.")



#-----------------------------------------------------------------------------------------------------------------------

class Silver_ticket_form(forms.Form):
    silver_ticket_name = forms.CharField(required=True,
                                         max_length=100,
                                         widget=forms.TextInput(attrs=
                                         {
                                             'placeholder': 'Activity name',
                                             'class': 'input',
                                             'style': "width: 20vw",
                                         }
                                         ))

    service_ntlm_hash = forms.CharField(required=False,
                                  max_length=100,
                                  widget=forms.TextInput(attrs=
                                  {
                                      'placeholder': 'Hash service account',
                                      'class': 'input',
                                      'style': "width: 20vw",
                                  }
                                  ))

    domain_name = forms.CharField(required=True,
                             max_length=100,
                             widget=forms.TextInput(attrs=
                             {
                                 'placeholder': 'Domain name',
                                 'class': 'input',
                                 'style': "width: 20vw",
                             }
                             ))

    domain_sid = forms.CharField(required=False,
                                 max_length=100,
                                 widget=forms.TextInput(attrs=
                                 {
                                     'placeholder': 'Domain sid',
                                     'class': 'input',
                                     'style': "width: 20vw",
                                 }
                                 ))

    spoofed_username = forms.CharField(required=False,
                                       max_length=100,
                                       widget=forms.TextInput(attrs=
                                       {
                                           'placeholder': 'Spoofed username',
                                           'class': 'input',
                                           'style': "width: 20vw",
                                       }
                                       ))

    spn = forms.CharField(required=False,
                                       max_length=100,
                                       widget=forms.TextInput(attrs=
                                       {
                                           'placeholder': 'SPN',
                                           'class': 'input',
                                           'style': "width: 20vw",
                                       }
                                       ))

    spn_and_hash = forms.ChoiceField(choices=(), required=False)
    spoofed_username_choice = forms.ChoiceField(choices=(), required=False)
    domain_sid_choice = forms.ChoiceField(choices=(), required=False)

    checkbox = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"onchange": "toggleInputs()", }))

    def clean(self):  #
        cleaned_data = super().clean()
        service_ntlm_hash = cleaned_data.get('service_ntlm_hash')
        domain_name = cleaned_data.get('domain_name')
        domain_sid = cleaned_data.get('domain_sid')
        spoofed_username = cleaned_data.get("spoofed_username")
        spn = cleaned_data.get("spn")
        spoofed_username_choice = cleaned_data.get("spoofed_username_choice")
        domain_sid_choice = cleaned_data.get("domain_sid_choice")
        spn_and_hash = cleaned_data.get("spn_and_hash")

        if not (service_ntlm_hash and domain_name and domain_sid and spoofed_username and spn) and not (
                spn_and_hash and domain_sid_choice and spoofed_username_choice and domain_name):

            raise forms.ValidationError("At least one field must be filled.")














#-----------------------------------------------------------------------------------------------------------------------

class My_app_addscenario(forms.Form):
    scenario_name = forms.CharField(required=True,
                               max_length=100,
                               widget=forms.TextInput(attrs=
                               {
                                   'placeholder': 'Scenario name',
                                   'class': 'input',
                                   'style': "width: 20vw",
                               }
                               ))

#-----------------------------------------------------------------------------------------------------------------------

class Scenario_add_activity(forms.Form):
    tactic_choice = forms.ChoiceField(choices=[("---", "---"), ('reconnaissance', 'reconaissance'), ('initial_access', 'Initial access'), ('persistence', 'Persistence'),
                                                ('privilege-escalation', 'Privilege escalation'), ('credential_access', 'Credential access'),
                                                ('discovery', 'discovery'), ('exfiltration', 'exfiltration'), ('lateral_mouvement', 'Lateral mouvement'), ("local", "Local"), ("others", "others")],
                                       widget=forms.Select(
                                           attrs={
                                               'required': True,
                                               'onchange': 'maj_technique_choice();',
                                           }

                                       ))

    technique_choice = forms.ChoiceField(choices=[],
                                         widget=forms.Select(
                                             attrs={
                                                 'required': True,
                                                 'onchange': 'maj_procedure_choice();'
                                             }
                                                             ))

    procedure_choice = forms.ChoiceField(choices=[],
                                         widget=forms.Select(
                                             attrs={
                                                 'required': True,
                                             }
                                         ))
