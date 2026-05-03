from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from .models import *
from .forms import *
from django.contrib import messages
from django.utils import timezone
from django.db.models import Max
import subprocess
from pymetasploit3.msfrpc import MsfRpcClient
import time
import os
import glob
import yaml
import re
from datetime import datetime
from urllib.parse import quote
from django.http import JsonResponse
from django.urls import reverse
from django.db.models import Q
from io import BytesIO
from django.http import HttpResponse
import json

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, LongTable
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import inch
from reportlab.lib import enums
from reportlab.lib import colors

import base64

# Create your views here.

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_workspaces(request):
    if request.method == "POST":

        if "workspace_name" in request.POST:
            form = My_app_addworkspace(request.POST)
            if form.is_valid():
                workspace_name = form.cleaned_data["workspace_name"]
                Workspaces.objects.create(user_id=request.user.id, name=workspace_name)

            form = My_app_addworkspace()
            queryset = Workspaces.objects.filter(user_id=request.user.id)

            contexte = {
                "workspace_list": queryset,
                "form": form,
            }
            return render(request, 'workspaces.html', contexte)

        elif "workspace_id" in request.POST:
            workspace_id = request.POST.get("workspace_id")
            form = Modify_workspace(request.POST)
            my_workspace = Workspaces.objects.get(user_id=request.user.id, id=workspace_id)


            if form.is_valid():

                if form.cleaned_data["domain_name"] and form.cleaned_data["domain_name"] != "":
                    domain_name = form.cleaned_data["domain_name"]
                    my_workspace.domain_name = domain_name
                    my_workspace.save()

                if form.cleaned_data["domain_user"] and form.cleaned_data["domain_user"] != "":
                    domain_user = form.cleaned_data["domain_user"]
                    my_workspace.domain_user = domain_user
                    my_workspace.save()

                if form.cleaned_data["user_password"] and form.cleaned_data["user_password"] != "":
                    user_password = form.cleaned_data["user_password"]
                    my_workspace.user_password = user_password
                    my_workspace.save()

            form = Modify_workspace()
            form.fields['workspace_id'].initial = workspace_id
            workspace_info = {
                "domain_name": str(my_workspace.domain_name),
                "domain_user": str(my_workspace.domain_user),

            }

            user_password = ""
            if my_workspace.user_password:
                user_password = "defined"
            else:
                user_password = "not defined"

            workspace_info["user_password"] = user_password

            contexte = {
                "form": form,
                "workspace_info": workspace_info,
            }

            return render(request, "modify_workspace/modify_workspace.html", contexte)


    else:
        if "workspace_id" in request.GET:
            workspace_id = request.GET.get("workspace_id")
            session = request.session
            session["workspace"] = workspace_id
            if "attack_session_uuid" in session:
                del session["attack_session_uuid"]
            session.save()

            # arreter le scenario si il y'en a (lors du changement de workspace)
            if "scenario_name" in session:

                messages.error(request,
                               "The scenario was stopped because the workspace has been changed")
                del session["scenario_name"]
                del session["scenario_steps"]
                del session["scenario_steps_length"]
                del session["current_scenario_step"]
                del session["current_scenario_step_status"]
                session.save()


            #---------------

            return redirect("My_app-activite")

        elif "modify_id" in request.GET:
            workspace_id = request.GET.get("modify_id")
            form = Modify_workspace()
            form.fields['workspace_id'].initial = workspace_id

            my_workspace = Workspaces.objects.get(user_id=request.user.id, id=workspace_id)
            workspace_info = {
                "domain_name": str(my_workspace.domain_name),
                "domain_user": str(my_workspace.domain_user),

            }

            user_password = ""
            if my_workspace.user_password:
                user_password = "defined"
            else:
                user_password = "not defined"

            workspace_info["user_password"] = user_password

            contexte = {
                "form": form,
                "workspace_info": workspace_info,
            }

            return render(request, "modify_workspace/modify_workspace.html", contexte)


        else:

            form = My_app_addworkspace()
            queryset = Workspaces.objects.filter(user_id=request.user.id)

            contexte = {
                "workspace_list": queryset,
                "form": form,
            }
            return render(request, 'workspaces.html', contexte)


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def get_workspace_info(request):
    workspace_info = {
        "domain_name": "",
        "domain_user": "",
        "user_password": "",
    }

    if "workspace" in request.session:
        workspace_id = request.session["workspace"]
        workspace = Workspaces.objects.get(user_id=request.user.id, id=workspace_id)
        workspace_domain_name = workspace.domain_name
        workspace_domain_user = workspace.domain_user
        workspace_user_password = workspace.user_password

        if not workspace_domain_name:
            workspace_domain_name = ""
        if not workspace_domain_user:
            workspace_domain_user = ""
        if not workspace_user_password:
            workspace_user_password = ""


        workspace_info["domain_name"] = workspace_domain_name
        workspace_info["domain_user"] = workspace_domain_user
        workspace_info["user_password"] = workspace_user_password

    return JsonResponse(workspace_info)



#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_activite(request):

    if "workspace" not in request.session:
        messages.error(request, "You must select a workspace first")
        return render(request, "activite.html", {})

    if request.method == "GET":

        if 'id' in request.GET:
            #Ceci est dans le cas ou un utilisateur a cliqué sur le bouton voir resultat d'une activité :
            activity = Activity.objects.get(id=request.GET.get('id'))

            if activity.user_id != request.user.id:
                messages.error(request, "This activity is not yours")
                return redirect("My_app-activite")


            print(activity.id)
            if activity.type == "Network scan":
                if activity.end_date is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_network_scan.html", {})
                else:
                    if not activity.results:
                        messages.error(request, "no results for this activity")
                        return render(request, "activite/resultats_network_scan.html", {})
                    else:
                        return render(request, "activite/resultats_network_scan.html", {'activity': activity})
            elif activity.type == "vuln scan":
                vulns = {}
                if activity.results and "result" in activity.results["get_reports_response"]["report"]["report"]["results"]:
                    for vuln in activity.results["get_reports_response"]["report"]["report"]["results"]["result"]:
                        vulns[vuln['@id']] = {
                            "name": vuln["name"],
                            "host": vuln["host"]["#text"],
                            "port": vuln["port"],
                            "severity": vuln["severity"],
                        }
                        list_ref = []
                        if vuln['nvt'].get('refs') is not None:
                            if isinstance(vuln['nvt']["refs"]["ref"], dict) and vuln['nvt']['refs']['ref'].get("@type") is not None:
                                vuln_ref = {
                                    "type": vuln['nvt']['refs']['ref']["@type"],
                                    "id": vuln['nvt']['refs']['ref']["@id"],
                                }
                                list_ref.append(vuln_ref)
                            else:
                                for reference in vuln["nvt"]["refs"]["ref"]:
                                    if reference.get("@type") is not None:
                                        vuln_ref = {
                                            "type": reference["@type"],
                                            "id": reference["@id"],

                                        }

                                        list_ref.append(vuln_ref)
                        if len(list_ref) != 0:
                            vulns[vuln["@id"]]["refs"] = list_ref

                else:
                    if activity.end_date is None:
                        messages.error(request, "The activity is not finished")
                        return render(request, "activite/resultats_vuln_scan.html", {})
                    else:
                        messages.error(request, "No results for this activity : There are either no hosts matching the specified IP address or no vulnerabilities present.")
                        return render(request, "activite/resultats_vuln_scan.html", {})


                return render(request, "activite/resultats_vuln_scan.html", {'vulns': vulns})

            elif activity.type == "Ldap enumeration":
                if activity.end_date is None:
                    messages.error(request, 'The activity is not finished')
                    return render(request, "activite/resultats_ldap_enum.html", {})
                else:
                    if not activity.results:
                        messages.error(request, "There was a problem establishing a connection to the server.")
                        return render(request, "activite/resultats_ldap_enum.html", {})
                    else:
                        contexte = {
                            "activity_results": activity.results,
                        }
                        return render(request, "activite/resultats_ldap_enum.html", contexte)

            elif activity.type == "SMB enumeration":
                if activity.end_date is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_smb_enum.html", {})
                else:
                    contexte = {
                        "activity_results": activity.results,
                    }
                    return render(request, "activite/resultats_smb_enum.html", contexte)




            elif activity.type == "T1110.002 - Password cracking":
                if activity.results is None: # on peut la laisser comme ca car dans tt les cas il y'a un resultats dans le cas ou il ne y'a pas ca veut dire que ce n'est pas terminé
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_password_cracking.html", {})
                else:
                    results = activity.results
                    # Dans le cas ou c'est un ticket tgs il faut traiter l'affichage du tgs
                    if "kerberos_ticket" in results:
                        if results["kerberos_ticket"] == "yes" and results["hash_value"]:

                            new_hash_value = ""

                            for i in range(0, len(results["hash_value"]), 70):
                                new_hash_value += results["hash_value"][i:i + 70] + "\n"
                            results["hash_value"] = new_hash_value

                    contexte = {
                        "results": results,
                    }
                    return render(request, "activite/resultats_password_cracking.html", contexte)









            elif activity.type == "Exploitation":
                if activity.results is None:
                    messages.error(request, "Exploitation of the vulnerability is in progress")
                    return render(request, "activite/resultats_exploitation.html", {})
                else:

                    if activity.results["status"] == False:
                        messages.error(request, "The attempt to exploit the vulnerability was unsuccessful.")
                        return render(request, "activite/resultats_exploitation.html", {})
                    elif activity.results["status"] == True:

                        # on vérifie si la session existe toujours :
                        client = MsfRpcClient('anis', ssl=True)
                        session_uuid = activity.results["session_uuid"]

                        found = False
                        for key, value in client.sessions.list.items():
                            if value["uuid"] == session_uuid:
                                found = True
                                break

                        if found == True:

                            # lancer le programme d'écoute:
                            subprocess.Popen(
                                ["python", "My_app/scripts/serveur_websocket.py",
                                ])

                            time.sleep(2)


                            # retourner la page


                            contexte = {
                                "session_uuid": session_uuid,
                            }
                            return render(request, "activite/resultats_exploitation.html", contexte)
                        else:
                            messages.error(request, "L'exploitation a expiré")
                            return render(request, "activite/resultats_exploitation.html", {})

            elif activity.type == "T1550.002 - Pass the hash":
                if activity.results is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_pth.html", {})
                else:
                    contexte = {
                        "results": activity.results,
                    }
                    return render(request, "activite/resultats_pth.html", contexte)

            elif activity.type == "T1003.006 - Dcsync":
                if activity.results is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_dcsync.html", {})
                else:
                    contexte = {
                        "results": activity.results,
                    }
                    return render(request, "activite/resultats_dcsync.html", contexte)

            elif activity.type == "T1558.001 - Golden ticket":
                if activity.results is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_golden_ticket.html", {})
                else:
                    contexte = {
                        "results": activity.results,
                    }
                    return render(request, "activite/resultats_golden_ticket.html", contexte)

            elif activity.type == "T1550.003 - Pass the ticket":
                if activity.end_date is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_ptt.html", {})
                else:
                    if activity.results is None:
                        messages.error(request, "no results for this activity")
                        return render(request, "activite/resultats_ptt.html", {})
                    else:
                        contexte = {
                            "results": activity.results,
                        }
                        return render(request, "activite/resultats_ptt.html", contexte)

            elif activity.type == "T1558.003 - Kerberoasting":
                if activity.end_date is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_kerberoasting.html", {})
                else:
                    if activity.results is None:
                        messages.error(request, "No results for this activity")
                        return render(request, "activite/resultats_kerberoasting.html", {})
                    else:

                        results = activity.results
                        if "services" in results:
                            if len(results["services"]) > 0:
                                for index in range(len(results["services"])):
                                    service = results["services"][index]
                                    new_hash_tgs = ""

                                    for i in range(0, len(service["service_compte_hash"]), 70):
                                        new_hash_tgs += service["service_compte_hash"][i:i + 70] + "\n"
                                    service["service_compte_hash"] = new_hash_tgs
                                    results["services"][index] = service


                        contexte = {
                            "results": results,
                        }
                        return render(request, "activite/resultats_kerberoasting.html", contexte)





            elif activity.type == "T1558.002 - Silver ticket":
                if activity.end_date is None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_silver_ticket.html", {})
                else:
                    if activity.results is None:
                        messages.error(request, "No results for this activity")
                        return render(request, "activite/resultats_silver_ticket.html", {})
                    else:

                        results = activity.results
                        contexte = {
                            "results": results,
                        }
                        return render(request, "activite/resultats_silver_ticket.html", contexte)













            elif activity.type == "Port listener":
                if activity.results is None:
                    messages.error(request, "The port is listening")
                    return render(request, "activite/resultats_port_listener.html", {})
                else:

                    if activity.results["status"] == False:
                        messages.error(request, "session establishment failed")
                        return render(request, "activite/resultats_port_listener.html", {})
                    elif activity.results["status"] == True:

                        # on vérifie si la session existe toujours :
                        client = MsfRpcClient('anis', ssl=True)
                        session_uuid = activity.results["session_uuid"]

                        found = False
                        for key, value in client.sessions.list.items():
                            if value["uuid"] == session_uuid:
                                found = True
                                break

                        if found == True:

                            # lancer le programme d'écoute:
                            subprocess.Popen(
                                ["python", "My_app/scripts/serveur_websocket.py",
                                ])

                            time.sleep(2)


                            # retourner la page


                            contexte = {
                                "session_uuid": session_uuid,
                            }
                            return render(request, "activite/resultats_port_listener.html", contexte)
                        else:
                            messages.error(request, "session expired")
                            return render(request, "activite/resultats_port_listener.html", {})



            else:
                results = activity.results
                if results == None:
                    messages.error(request, "The activity is not finished")
                    return render(request, "activite/resultats_post_exp.html", {})
                else:
                    contexte = {
                        "results": results['commands'],
                        "procedure": results['procedure'],

                    }

                    if "traitement" in results:
                        contexte["traitement"] = results["traitement"]
                    return render(request, "activite/resultats_post_exp.html", contexte)


        elif "activity_id" in request.GET:
            activity = Activity.objects.get(id=request.GET.get('activity_id'))


            if activity.user_id != request.user.id:

                messages.error(request, "This activity is not yours")
                return redirect("My_app-activite")


            begin_date = activity.begin_date.strftime('%Y-%m-%dT%H:%M:%S.%f')
            end_date = ""
            if activity.end_date != None:
                end_date = activity.end_date.strftime('%Y-%m-%dT%H:%M:%S.%f')

            print("begin date ----->" + str(begin_date))
            print("end date ------->" + str(end_date))

            # Lecture du fichier de configuration:
            with open("My_app/config.yml", 'r') as file:
                yaml_data = yaml.safe_load(file)

            index_pattern = None
            source_ip = yaml_data["local_host"]
            target_ips = []
            query = None
            if activity.results != None and activity.results:
                if activity.type == "Network scan" or activity.type == "vuln scan" or activity.type == "Ldap enumeration" or activity.type == "SMB enumeration":
                    index_pattern = 'packetbeat-*'
                    if activity.type == "Network scan":
                        activity_result = activity.results
                        for ip, value in activity_result.items():
                            target_ips.append(ip)
                        query = ""
                        for ip in target_ips:
                            filtre = "(host.ip: " + ip + " and ((destination.ip: " + ip + " and source.ip: " + source_ip + ") or (destination.ip: " + source_ip + " and source.ip: " + ip + ")))"
                            query = query + filtre + " or "
                        query = query[:-3]
                    elif activity.type == "vuln scan":
                        if "result" in activity.results["get_reports_response"]["report"]["report"]["results"]:
                            for vuln in activity.results["get_reports_response"]["report"]["report"]["results"]["result"]:
                                if vuln["host"]["#text"] not in target_ips:
                                    target_ips.append(vuln["host"]["#text"])

                            query = ""
                            for ip in target_ips:
                                filtre = "(host.ip: " + ip + " and ((destination.ip: " + ip + " and source.ip: " + source_ip + ") or (destination.ip: " + source_ip + " and source.ip: " + ip + ")))"
                                query = query + filtre + " or "
                            query = query[:-3]

                        else:
                            messages.error(request, "There are either no hosts matching the specified IP address")
                    elif activity.type == "Ldap enumeration":
                        ip = activity.results["enumerated_machine"]
                        filtre = "(host.ip: " + ip + " and ((destination.ip: " + ip + " and source.ip: " + source_ip + ") or (destination.ip: " + source_ip + " and source.ip: " + ip + ")))"
                        query = filtre
                    elif activity.type == "SMB enumeration":
                        activity_result = activity.results
                        for ip, value in activity_result.items():
                            target_ips.append(ip)

                        query = ""
                        for ip in target_ips:
                            filtre = "(host.ip: " + ip + " and ((destination.ip: " + ip + " and source.ip: " + source_ip + ") or (destination.ip: " + source_ip + " and source.ip: " + ip + ")))"
                            query = query + filtre + " or "
                        query = query[:-3]





                elif activity.type == "Exploitation":
                    result = activity.results
                    if "session_os" in result:
                        session_os = result["session_os"]
                        if session_os == "linux" or "session_os" == "macos":
                            index_pattern = "filebeat-*"
                        else:
                            index_pattern = "winlogbeat-*"
                        query = "host.ip: " + result["target_ip"]
                    else:
                        index_pattern = "winlogbeat-*"
                        query = "host.ip: " + result["target_ip"]


                elif activity.type == "T1550.002 - Pass the hash":
                    result = activity.results
                    target_ips = []
                    username = result["username"]
                    index_pattern = "winlogbeat-*"
                    for host in result["hosts"]:
                        target_ips.append(host["host_ip"])

                    query = ""
                    for ip in target_ips:
                        filtre = "host.ip: " + ip
                        query = query + filtre + " or "
                    query = query[:-3]

                    query = "((" + query + ") and ((event.code: 4624 and user.name: " + str(username) + " and winlog.event_data.LogonType: 3) or (event.code: 4672 and user.name: " + str(username) +")))"




                elif activity.type == "T1003.006 - Dcsync":
                    result = activity.results
                    target_ip = result["target_ip"]
                    username_admin = result["username_admin"]

                    # verifier si le target_ip est une address ip ou bien un dns host name
                    pattern = r"[a-zA-Z]"
                    match = re.search(pattern, target_ip)
                    if match:

                        # target_ip est un dns host name on doit le traduire en address ip
                        session = request.session
                        smb_enum_activities = Activity.objects.filter(type="SMB enumeration",user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
                        if len(smb_enum_activities) > 0:
                            for smb_enum_activity in smb_enum_activities:
                                exist = False
                                if smb_enum_activity.results != None and smb_enum_activity.results:

                                    for host, host_info in smb_enum_activity.results.items():
                                        if "FQDN" in host_info and "host_ip" in host_info:
                                            if host_info["FQDN"] and host_info["host_ip"]:
                                                if host_info["FQDN"] == " " + str(target_ip):
                                                    target_ip = host_info["host_ip"]
                                                    exist = True
                                                    break
                                    if exist == True:
                                        break



                    print("target_ip : " + str(target_ip))
                    query = "host.ip: " + target_ip
                    query = query + " and winlog.event_data.SubjectUserName: " + str(username_admin) + " and event.code: 4662"
                    index_pattern = "winlogbeat-*"

                elif activity.type == "T1550.003 - Pass the ticket":

                    result = activity.results
                    target_ips = []
                    username = result["username"]

                    if len(result["hosts"]) > 0:
                        index_pattern = "winlogbeat-*"
                        for host in result["hosts"]:
                            target_ips.append(host["host_ip"])

                        query = ""
                        for ip in target_ips:
                            filtre = "host.ip: " + ip
                            query = query + filtre + " or "
                        query = query[:-3]

                        query = "((" + query + ") and ((event.code : 4769 and user.name: " + str(username) + ") or (event.code: 4672 and user.name: " + str(username) + ") or (event.code: 4624 and user.name: " + str(username) + " and winlog.event_data.LogonType: 3)))"

                    else:
                        messages.error(request, "No interaction with other machines")

                elif activity.type == "T1558.003 - Kerberoasting":
                    result = activity.results


                    target_ip = result["dc_ip"]

                    # verifier si le target_ip est une address ip ou bien un dns host name
                    pattern = r"[a-zA-Z]"
                    match = re.search(pattern, target_ip)
                    if match:

                        # target_ip est un dns host name on doit le traduire en address ip
                        session = request.session
                        smb_enum_activities = Activity.objects.filter(type="SMB enumeration",
                                                                      user_id=request.user.id,
                                                                      workspace_id=session["workspace"],
                                                                      results__isnull=False)
                        if len(smb_enum_activities) > 0:
                            for smb_enum_activity in smb_enum_activities:
                                exist = False
                                if smb_enum_activity.results != None and smb_enum_activity.results:

                                    for host, host_info in smb_enum_activity.results.items():
                                        if "FQDN" in host_info and "host_ip" in host_info:
                                            if host_info["FQDN"] and host_info["host_ip"]:
                                                if host_info["FQDN"] == " " + str(target_ip):
                                                    target_ip = host_info["host_ip"]
                                                    exist = True
                                                    break
                                    if exist == True:
                                        break

                    print("target_ip : " + str(target_ip))
                    query = "host.ip: " + target_ip

                    index_pattern = "winlogbeat-*"





                elif activity.type == "Port listener":
                    messages.error(request, "it's a listening port, no traces")
                elif activity.type == "T1110.002 - Password cracking":
                    messages.error(request, "Password cracking is done locally on the machine so there are no traces")
                elif activity.type == "T1558.001 - Golden ticket":
                    messages.error(request, "The act of forging golden tickets is performed on the local machine.")
                elif activity.type == "T1558.002 - Silver ticket":
                    messages.error(request, "The act of forging silver tickets is performed on the local machine.")


                else:
                    result = activity.results
                    if "session_os" in result:
                        if result["session_os"] == "linux" or result["session_os"] == "macos":
                            index_pattern = "filebeat-*"
                        elif result["session_os"] == "windows":
                            index_pattern = "winlogbeat-*"
                        query = "host.ip: " + result["target_address"]
            else:
                messages.error(request, "The technique has not yet completed or has failed.")


            contexte = {
                "index_pattern": index_pattern,
                "begin_date": begin_date,
                "end_date": end_date,
                "query": query,

            }

            return render(request, "activite/traces.html", contexte)





        session = request.session
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"])
        contexte = {
            'activities': activities,
        }
        return render(request, 'activite.html', contexte)

    elif request.method == "POST":
        attack_session_uuid = request.POST.get("session_uuid")
        print(attack_session_uuid)
        session = request.session
        session["attack_session_uuid"] = attack_session_uuid
        return redirect("My_app-attacks")


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_attacks(request):
    if "workspace" in request.session:

        contexte = {
            'afficher': True,
            'attacks': None,
            'ttps': None,
        }


        if "scenario_name" in request.session:
            if "session_uuid" in request.session:
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! " + request.session["session_uuid"])
            scenario_name = request.session["scenario_name"]
            scenario_steps = request.session["scenario_steps"]
            scenario_steps_length = request.session["scenario_steps_length"]
            current_scenario_step = request.session["current_scenario_step"]
            current_scenario_step_status = request.session["current_scenario_step_status"]
            session = request.session

            print(scenario_name)
            print(current_scenario_step)
            print(current_scenario_step_status)


            # dans le cas ou il y'a deja une etape en cours qui n'a pas terminé on doit attendre:
            if current_scenario_step_status == "running":
                current_step_id = request.session["current_step_id"]
                activity = Activity.objects.get(id=current_step_id)

                #dans le cas ou l'activité (étape) n'a pas terminé:
                if activity.end_date == None:
                    messages.error(request, "You must wait for the completion of the current step")
                    contexte["afficher"] = False
                    return render(request, "attacks.html", contexte)
                #dans le cas ou l'activité (étape) a terminé:
                else:
                    if activity.type == "Exploitation":
                        if "session_uuid" not in activity.results:
                            messages.error(request, "the scenario was stopped because the exploitation did not work")
                            del session["scenario_name"]
                            del session["scenario_steps"]
                            del session["scenario_steps_length"]
                            del session["current_scenario_step"]
                            del session["current_scenario_step_status"]
                            session.save()
                            return render(request, 'attacks.html', contexte)
                        else:
                            session["session_uuid"] = activity.results["session_uuid"]

                    else:
                        index_old_port_listener = None
                        index_old_exploitation = None
                        for index in range(current_scenario_step + 1):
                            if session["scenario_steps"][index]["procedure"] == "Exploitation":
                                index_old_exploitation = index
                            elif session["scenario_steps"][index]["procedure"] == "port_listener":
                                index_old_port_listener = index
                        if index_old_port_listener != None:
                            if index_old_exploitation == None:
                                activity_id = session["scenario_steps"][index_old_port_listener]["activity_id"]
                                # on doit recuperer les resultat de cette activité :
                                activity = Activity.objects.get(id=activity_id)

                                if activity.results != None:
                                    status = activity.results["status"]
                                    if status == True:
                                        session["session_uuid"] = activity.results["session_uuid"]

                            else:
                                if index_old_port_listener > index_old_exploitation:
                                    activity_id = session["scenario_steps"][index_old_port_listener]["activity_id"]
                                    # on doit recuperer les resultat de cette activité :
                                    activity = Activity.objects.get(id=activity_id)

                                    if activity.results != None:
                                        status = activity.results["status"]
                                        if status == True:
                                            session["session_uuid"] = activity.results["session_uuid"]




                    current_session_step = current_scenario_step + 1
                    session["current_scenario_step"] = current_session_step
                    session["current_scenario_step_status"] = "sleeping"
                    session.save()
                    return redirect("My_app-attacks")

            elif current_scenario_step_status == "sleeping":
                if current_scenario_step > scenario_steps_length - 1:
                    messages.error(request, "the scenario is over")
                    del session["scenario_name"]
                    del session["scenario_steps"]
                    del session["scenario_steps_length"]
                    del session["current_scenario_step"]
                    del session["current_scenario_step_status"]
                    session.save()
                    return render(request, 'attacks.html', contexte)
                else:
                    step = scenario_steps[current_scenario_step]
                    if step["procedure"] == "network_scan":
                        return redirect("attacks-network_scan")
                    elif step["procedure"] == "vuln_scan":
                        return redirect("attacks-vuln_scan")
                    elif step["procedure"] == "ldap_enum":
                        return redirect("attacks-ldap_enum")
                    elif step["procedure"] == "smb_enum":
                        return redirect("attacks-smb_enum")
                    elif step["procedure"] == "port_listener":
                        return redirect("attacks-port_listener")
                    elif step["procedure"] == "password_cracking_john":
                        return redirect("attacks-password_cracking")
                    elif step["procedure"] == "pth_crackmapexec":
                        return redirect("attacks-pth")
                    elif step["procedure"] == "golden_ticket_ticketer":
                        return redirect("attacks-golden_ticket")
                    elif step["procedure"] == "dcsync_secretdump":
                        return redirect("attacks-dcsync")
                    elif step["procedure"] == "ptt_crackmapexec":
                        return redirect("attacks-ptt")
                    elif step["procedure"] == "kerberoasting_impacket":
                        return redirect("attacks-kerberoasting")
                    elif step["procedure"] == "silver_ticket_impacket":
                        return redirect("attacks-silver_ticket")

                    elif step["procedure"] == "exploitation":
                        return redirect("attacks-exploitation")
                    else:
                        url = reverse("attacks-post_exp")
                        url = url + "?procedure=" + quote(step["procedure"]) + "&tactic=" + quote(step["tactic"]) +\
                              "&technique=" + quote(step["technique"]) + "&uuid=" + session["session_uuid"]
                        return redirect(url)




        if "step" in request.GET:
            if request.GET.get("step") == "Reconnaissance":

                # ici on doit verifier par rapport a ce qu'on a dans la bdd comme information pour lui afficher uniquement les attaques de reconnaissance qu'il peut effectuer
                # Pour l'instant je vais le laisser faire du scan réseau et du scan de vulnérabilité
                attacks = {
                    "T1595.001 - Scanning ip blocks" : {"lien": 'attacks-network_scan', "description": "In order to gather information about victim networks, adversaries might scan IP blocks, obtaining details about which IP addresses are currently active and obtaining more specific information about the hosts associated with those addresses. These scans can vary from basic pings (ICMP requests and responses) to more sophisticated scans that can disclose details about the host's software and versions through server banners or other network artifacts.",},
                    "T1595.002 - Vulnerability Scanning" : {"lien" : 'attacks-vuln_scan', "description" : "During targeting, adversaries have the capability to scan victims for vulnerabilities that can be exploited."},


                    }


                contexte["attacks"] = attacks

            elif request.GET.get("step") == "InitialAccess":
                session = request.session
                # on doit vérifier par rapport a ce qu'on a dans la bdd
                activities = Activity.objects.filter(type="vuln scan", user_id=request.user.id,
                                                     workspace_id=session["workspace"], results__isnull=False)
                if len(activities) > 0:
                
                    attacks = {
                        "Exploit vulnerability": {"lien" : 'attacks-exploitation', "description": "Vulnerability exploitation involves the deliberate act of identifying and taking advantage of security weaknesses or vulnerabilities in systems, software, or networks. Attackers exploit these vulnerabilities to gain unauthorized access, compromise data, execute malicious code, or carry out other nefarious activities",},
                    }

                    contexte["attacks"] = attacks

            elif request.GET.get("step") == "lateral_mouvement":
                session = request.session
                activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(type="T1003.002-Dump-SAM-With-Mimikatz") | Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                                                     workspace_id=session["workspace"], results__isnull=False)

                attacks = {}
                if len(activities) > 0:
                    attacks["T1550.002 - Pass the hash"] = {"lien": "attacks-pth", "description": "By utilizing purloined password hashes, adversaries can engage in pass the hash techniques to traverse laterally within an environment, effectively bypassing standard system access controls. Pass the hash (PtH) refers to a method of authentication that enables adversaries to authenticate as a user without having access to the user's plaintext password"}


                activities = Activity.objects.filter(type="T1558.001 - Golden ticket", user_id=request.user.id, workspace_id=session["workspace"], results__isnull=False)
                if len(activities) > 0:
                    attacks["T1550.003 - Pass the ticket"] = {"lien": "attacks-ptt", "description": "Adversaries have the ability to utilize stolen Kerberos tickets in order to perform lateral movement within an environment, bypassing regular system access controls. Pass the ticket (PtT) refers to the technique of authenticating to a system using Kerberos tickets, even without knowledge of the account's password. Kerberos authentication serves as the initial stage for executing lateral movement towards a remote system"}

                contexte["attacks"] = attacks




            elif request.GET.get("step") == "Others":
                attacks = {
                    "Add a port listener": {"lien" : "attacks-port_listener", "description" : "allows an attacker to actively listen for incoming connections on a specific port on his own machine. This eavesdropping allows the attacker to receive a reverse shell session from a compromised target, thereby establishing remote access to that machine.",},
                }

                contexte["attacks"] = attacks
            else:
                session = request.session
                if "attack_session_uuid" in session:
                    attack_session_uuid = session["attack_session_uuid"]
                    print("attack_session_uuid = " + attack_session_uuid)
                    attack_session_uuid = attack_session_uuid[13:]
                    # on vérifie si la session existe toujours :
                    client = MsfRpcClient('anis', ssl=True)

                    found = False
                    meterpreter = False
                    for key, value in client.sessions.list.items():
                        if value["uuid"] == attack_session_uuid:
                            found = True
                            if value["type"] == "meterpreter":
                                meterpreter = True
                            break
                    print(meterpreter)
                    if found == False:
                        del session["attack_session_uuid"]
                        messages.error(request, "La session n'existe plus")
                        #return render(request, 'attacks.html', {})
                    else:
                        origin_dir_path = os.path.abspath(os.getcwd())
                        tactic = request.GET.get("step")
                        tactic_directory = os.path.join("My_app/scripts/atomics", tactic)

                        # se connecter a la session_uuid
                        #shell = client.sessions.session(attack_session_uuid)


                        # recuperer les information de la session 'user connecré et l'os et les groupes d'user) mise a jour
                        activities = Activity.objects.filter(Q(type="Exploitation") | Q(type="Port listener"), user_id=request.user.id,
                                                             workspace_id=session["workspace"], results__isnull=False)

                        attack_session_os = None
                        attack_session_user = None
                        user_groups = None
                        for activity in activities:
                            if "session_uuid" in activity.results:
                                if activity.results["session_uuid"] == attack_session_uuid:
                                    attack_session_os = activity.results["session_os"]
                                    attack_session_user = activity.results["session_user"]
                                    user_groups = activity.results["user_groups"]
                                    break

                        print("attacl_session_os = " + attack_session_os)
                        print("attack_session_user = " + attack_session_user)
                        print("user_groups = " + user_groups)
                        '''
                        # recuperer les information de la sessions (utilisateur connecté et l'os)
                        if meterpreter == True:
                            shell.write("shell")
                            time.sleep(2)
                            shell.read()

                        shell.write("whoami")
                        time.sleep(1)
                        output_whoami = shell.read()
                        print("---------->" + output_whoami)
                        attack_session_os = None
                        attack_session_user = None
                        for key, value in client.sessions.list.items():
                            if value["uuid"] == attack_session_uuid:
                                if value["type"] == "meterpreter":
                                    attack_session_os = value["platform"]
                                else:
                                    shell.write("uname -a")
                                    #time.sleep(1)
                                    uname_output = shell.read()
                                    print("---------> uname output = " + uname_output)
                                    if "Linux" in uname_output:
                                        attack_session_os = "linux"
                                    elif "Darwin" in uname_output:
                                        attack_session_os = "macos"
                                    else:
                                        attack_session_os = "windows"
                                break
                        if attack_session_os == "linux" or attack_session_os == "macos":
                            attack_session_user = output_whoami
                        else:
                            match = re.search(r'(?<=whoami\n).*(?=\r)', output_whoami)
                            if match:
                                attack_session_user = match.group()
                            else:
                                print("Le contenu spécifié n'a pas été trouvé.")
                        print("attack_session_os = " + attack_session_os)
                        print("attack_session_user = " + attack_session_user)
                        '''



                        #--------------- Traitement pour afficher les TTPs -------------
                        # --------------------------------------------------------------
                        # Récupère le chemin absolu du répertoire courant
                        os.chdir(tactic_directory)
                        dir_path = os.path.abspath(os.getcwd())

                        attack_techniques = {}  # Dictionnaire qui stocke toutes les techniques

                        if request.GET.get("step") == "credential_access":

                            # Traitement pour voir si on affiche ou non le silver ticket
                            lsass_activities = Activity.objects.filter(
                                Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
                                    type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                                workspace_id=session["workspace"], results__isnull=False)
                            afficher1 = False
                            for activity in lsass_activities:
                                if activity.results and "traitement" in activity.results:
                                    if activity.results["traitement"]:
                                        afficher1 = True
                                        break

                            ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration",
                                                                           user_id=request.user.id,
                                                                           workspace_id=session["workspace"],
                                                                           results__isnull=False)
                            afficher2 = False
                            for activity in ldap_enum_activities:
                                if activity.results:
                                    afficher2 = True
                                    break

                            password_cracking_activities = Activity.objects.filter(type="T1110.002 - Password cracking",
                                                                           user_id=request.user.id,
                                                                           workspace_id=session["workspace"],
                                                                           results__isnull=False)

                            afficher3 = False
                            for password_cracking_activity in password_cracking_activities:
                                if password_cracking_activity.results:
                                    password_cracking_results = password_cracking_activity.results

                                    if "service_ntlm_hash" in password_cracking_results:
                                        if password_cracking_results["service_ntlm_hash"]:
                                            afficher3 = True
                                            break

                            if afficher1 == True and afficher2 == True and afficher3 == True:
                                attack_techniques["T1558.002"] = {
                                    "name": "Silver ticket",
                                    "tactic": request.GET.get("step"),
                                    "url": "attacks-silver_ticket",
                                    "description": "Service tickets, also referred to as Kerberos TGS tickets, can be forged by adversaries possessing the password hash of a target service account (such as SharePoint or MSSQL). These forged tickets are commonly known as silver tickets.",

                                }





                            attack_techniques["T1558.003"] = {
                                "name": "Kerberoasting",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-kerberoasting",
                                "description": "Plaintext credentials may be exposed through offline Brute Force attacks when adversaries with a valid Kerberos ticket-granting ticket (TGT) request one or more Kerberos ticket-granting service (TGS) service tickets for any SPN from a domain controller (DC). These tickets may have portions encrypted with the RC4 algorithm, where the private key is the Kerberos 5 TGS-REP etype 23 hash of the service account linked to the SPN, making it susceptible to vulnerability.",

                            }



                            #Traitement pour voir si on affiche ou non le local password cracking
                            dump_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(type="T1003.005-Cached Credential Dump via Mimikatz") | Q(type="T1003.002-Dump-SAM-With-Mimikatz") | Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"),
                                                                 user_id=request.user.id,
                                                                 workspace_id=session["workspace"],
                                                                 results__isnull=False)
                            afficher = False
                            for activity in dump_activities:
                                if activity.results and "traitement" in activity.results:
                                    if activity.results["traitement"]:
                                        afficher = True
                                        break

                            kerberoasting_activities = Activity.objects.filter(type="T1558.003 - Kerberoasting",
                                                                 user_id=request.user.id,
                                                                 workspace_id=session["workspace"],
                                                                 results__isnull=False)
                            afficher2 = False
                            for activity in kerberoasting_activities:
                                if activity.results and "services" in activity.results:
                                    if len(activity.results["services"]) > 0:
                                        afficher2 = True
                                        break


                            if afficher == True or afficher2 == True:
                                attack_techniques["T1110.002"] = {
                                    "name": "Local password cracking",
                                    "tactic": request.GET.get("step"),
                                    "url": "attacks-password_cracking",
                                    "description" : "Local password cracking allows passwords recovered by other techniques to be decrypted by decrypting them locally.",

                                }

                            # Traitement pour voir si on affiche ou non le dcsync
                            lsass_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id, workspace_id=session["workspace"], results__isnull=False)
                            afficher1 = False
                            for activity in lsass_activities:
                                if activity.results and "traitement" in activity.results:
                                    if activity.results["traitement"]:
                                        afficher1 = True
                                        break

                            ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration", user_id=request.user.id, workspace_id=session["workspace"], results__isnull=False)
                            afficher2 = False
                            for activity in ldap_enum_activities:
                                if activity.results:
                                    afficher2 = True
                                    break

                            if afficher1 == True and afficher2 == True:
                                attack_techniques["1003.006"] = {
                                    "name": "OS Credential Dumping: DCSync",
                                    "tactic": request.GET.get("step"),
                                    "url": "attacks-dcsync",
                                    "description": "Using a technique called DCSync, adversaries may exploit the application programming interface (API) of a Windows Domain Controller to simulate the replication process from a remote domain controller, aiming to gain unauthorized access to credentials and other sensitive information.",
                                }

                            #traiter pour voir si on affiche ou non le golden ticket
                            lsass_activities = Activity.objects.filter(
                                Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
                                    type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                                workspace_id=session["workspace"], results__isnull=False)

                            afficher1 = False
                            for activity in lsass_activities:
                                if activity.results and "traitement" in activity.results:
                                    if activity.results["traitement"]:
                                        afficher1 = True
                                        break

                            ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration",
                                                                           user_id=request.user.id,
                                                                           workspace_id=session["workspace"],
                                                                           results__isnull=False)
                            afficher2 = False
                            for activity in ldap_enum_activities:
                                if activity.results:
                                    afficher2 = True
                                    break

                            dcsync_activities = Activity.objects.filter(type="T1003.006 - Dcsync",
                                                                           user_id=request.user.id,
                                                                           workspace_id=session["workspace"],
                                                                           results__isnull=False)

                            afficher3 = False
                            for activity in dcsync_activities:
                                if activity.results and "creds" in activity.results:
                                    if len(activity.results["creds"]) > 0:
                                        afficher3 = True
                                        break
                            if afficher1 == True and afficher2 == True and afficher3 == True:

                                attack_techniques["T1558.001"] = {
                                    "name": "Forge Kerberos Tickets: Golden Ticket",
                                    "tactic": request.GET.get("step"),
                                    "url": "attacks-golden_ticket",
                                    "description": "Having possession of the KRBTGT account password hash empowers adversaries to fabricate Kerberos ticket-granting tickets (TGT), commonly referred to as golden tickets. These golden tickets provide adversaries with the ability to produce authentication credentials for any account within the Active Directory system."
                                }


                        if request.GET.get("step") == "discovery":
                            attack_techniques["T1078.002"] = {
                                "name": "Ldap enumeration",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-ldap_enum",
                                "description": "retrieve a list of accounts in a target environment",
                            }

                            attack_techniques["T1078"] = {
                                "name": "SMB enumeration",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-smb_enum",
                                "description": "Process in which we enumerate the host or target system for different information",
                            }














                        # Parcourt chaque élément dans le répertoire courant
                        for element in os.listdir(dir_path):
                            # Vérifie si l'élément est un répertoire
                            if os.path.isdir(os.path.join(dir_path, element)):
                                # Entre dans le répertoire
                                os.chdir(element)
                                # Récuperer tout les fichiers qui se terminent par .yaml
                                yaml_files = glob.glob("*yaml")

                                # Ouvre le fichier YAML en mode lecture
                                with open(yaml_files[0], 'r') as file:
                                    # Charge le contenu du fichier YAML
                                    yaml_data = yaml.safe_load(file)

                                # je vérifie si la technique contient un test atomic qui satisfait mes privs et l'os de la session
                                # Accède aux champs attack_technique et display_name et atomic_tests
                                attack_technique = yaml_data['attack_technique']
                                display_name = yaml_data['display_name']
                                atomic_tests = yaml_data["atomic_tests"]

                                satisfait = False
                                procedure_names = [] #
                                for atomic_test in atomic_tests:
                                    procedure_names = [] #
                                    satisfait = False
                                    atomic_test_platform = atomic_test["supported_platforms"]
                                    if attack_session_os in atomic_test_platform:
                                        atomic_test_executor = atomic_test["executor"]
                                        if "elevation_required" not in atomic_test_executor:
                                            satisfait = True
                                            #break
                                        else:
                                            if atomic_test_executor["elevation_required"] == "false":
                                                satisfait = True
                                                #break
                                            else:
                                                # on verifie si l'user actuelle a des privs admin
                                                if "root" in attack_session_user or r"autorite nt\sys" in attack_session_user: # si l'user est root (represente root dans linux+macos) et system dans windows)
                                                    satisfait = True
                                                    #break
                                                elif attack_session_os == "windows": # sinon si on est sur windows on vérifie si l'user appartient au groupe admin
                                                    #shell.write("whoami /groups")
                                                    #time.sleep(1)
                                                    #output = shell.read()
                                                    #print("-------------> output_windows_whoami_groups = " + output)

                                                    if "Administrateurs" in user_groups or "Administrators" in user_groups:
                                                        satisfait = True
                                                        #break
                                                elif attack_session_os == "linux":
                                                    #shell.write("groups")
                                                    #time.sleep(1)
                                                    #output = shell.read()
                                                    #print("---------> output groups" + output)
                                                    if "root" in user_groups:
                                                        satisfait = True
                                                        #break
                                                elif attack_session_os == "macos":
                                                    #shell.write("groups")
                                                    #time.sleep(1)
                                                    #output = shell.read()
                                                    #print("--------->output groups macos = " + output)
                                                    if "wheel" in user_groups:
                                                        satisfait = True
                                                        #break


                                    if meterpreter == False:
                                        executor_name = atomic_test["executor"]["name"]
                                        if executor_name == "powershell":
                                            satisfait = False
                                        elif satisfait == True:
                                            break
                                    elif satisfait == True:
                                        break



                                #procedure_names = '\n'.join(['- ' + procedure_name for procedure_name in procedure_names])




                                if satisfait == True:
                                    for atomic_test in atomic_tests:
                                        procedure_names.append(atomic_test["name"])
                                    procedure_names = '\n'.join(
                                        ['- ' + procedure_name for procedure_name in procedure_names])

                                    technique_info = {
                                        "name": display_name,
                                        "tactic": request.GET.get("step"),
                                        "procedure_names" : procedure_names,
                                    }
                                    attack_techniques[attack_technique] = technique_info

                                os.chdir(dir_path)  # retourne au répertoire courant


                        #juste un affichage pour voir si il a recuperer les techniques ou non
                        for technique_id, technique_info in attack_techniques.items():
                            print("technique id: " + str(technique_id) + "---->" + str(technique_info["name"]))

                        # retourner les ttps
                        contexte["techniques"] = attack_techniques
                        contexte["session_uuid"] = attack_session_uuid

                        #if meterpreter == True:
                         #   shell.write("exit")
                          #  shell.read()
                        # on doit retourner vers le repertoire d'origine quand on termine
                        os.chdir(origin_dir_path)
                else:
                    #---------Dans le cas d'affichage de nos ttps  credential access sans session----------------------
                    attack_techniques = {}  # Dictionnaire qui stocke toutes les techniques

                    if request.GET.get("step") == "credential_access":

                        # Traitement pour voir si on affiche ou non le silver ticket
                        lsass_activities = Activity.objects.filter(
                            Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
                                type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                            workspace_id=session["workspace"], results__isnull=False)
                        afficher1 = False
                        for activity in lsass_activities:
                            if activity.results and "traitement" in activity.results:
                                if activity.results["traitement"]:
                                    afficher1 = True
                                    break

                        ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration",
                                                                       user_id=request.user.id,
                                                                       workspace_id=session["workspace"],
                                                                       results__isnull=False)
                        afficher2 = False
                        for activity in ldap_enum_activities:
                            if activity.results:
                                afficher2 = True
                                break

                        password_cracking_activities = Activity.objects.filter(type="T1110.002 - Password cracking",
                                                                               user_id=request.user.id,
                                                                               workspace_id=session["workspace"],
                                                                               results__isnull=False)

                        afficher3 = False
                        for password_cracking_activity in password_cracking_activities:
                            if password_cracking_activity.results:
                                password_cracking_results = password_cracking_activity.results

                                if "service_ntlm_hash" in password_cracking_results:
                                    if password_cracking_results["service_ntlm_hash"]:
                                        afficher3 = True
                                        break

                        if afficher1 == True and afficher2 == True and afficher3 == True:
                            attack_techniques["T1558.002"] = {
                                "name": "Silver ticket",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-silver_ticket",
                                "description": "Service tickets, also referred to as Kerberos TGS tickets, can be forged by adversaries possessing the password hash of a target service account (such as SharePoint or MSSQL). These forged tickets are commonly known as silver tickets.",

                            }

                        attack_techniques["T1558.003"] = {
                            "name": "Kerberoasting",
                            "tactic": request.GET.get("step"),
                            "url": "attacks-kerberoasting",
                            "description": "Plaintext credentials may be exposed through offline Brute Force attacks when adversaries with a valid Kerberos ticket-granting ticket (TGT) request one or more Kerberos ticket-granting service (TGS) service tickets for any SPN from a domain controller (DC). These tickets may have portions encrypted with the RC4 algorithm, where the private key is the Kerberos 5 TGS-REP etype 23 hash of the service account linked to the SPN, making it susceptible to vulnerability.",

                        }

                        # Traitement pour voir si on affiche ou non le local password cracking
                        dump_activities = Activity.objects.filter(
                            Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
                                type="T1003.005-Cached Credential Dump via Mimikatz") | Q(
                                type="T1003.002-Dump-SAM-With-Mimikatz") | Q(
                                type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"),
                            user_id=request.user.id,
                            workspace_id=session["workspace"],
                            results__isnull=False)
                        afficher = False
                        for activity in dump_activities:
                            if activity.results and "traitement" in activity.results:
                                if activity.results["traitement"]:
                                    afficher = True
                                    break

                        kerberoasting_activities = Activity.objects.filter(type="T1558.003 - Kerberoasting",
                                                                           user_id=request.user.id,
                                                                           workspace_id=session["workspace"],
                                                                           results__isnull=False)
                        afficher2 = False
                        for activity in kerberoasting_activities:
                            if activity.results and "services" in activity.results:
                                if len(activity.results["services"]) > 0:
                                    afficher2 = True
                                    break

                        if afficher == True or afficher2 == True:
                            attack_techniques["T1110.002"] = {
                                "name": "Local password cracking",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-password_cracking",
                                "description": "Local password cracking allows passwords recovered by other techniques to be decrypted by decrypting them locally.",

                            }

                        # Traitement pour voir si on affiche ou non le dcsync
                        lsass_activities = Activity.objects.filter(
                            Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
                                type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                            workspace_id=session["workspace"], results__isnull=False)
                        afficher1 = False
                        for activity in lsass_activities:
                            if activity.results and "traitement" in activity.results:
                                if activity.results["traitement"]:
                                    afficher1 = True
                                    break

                        ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration", user_id=request.user.id,
                                                                       workspace_id=session["workspace"],
                                                                       results__isnull=False)
                        afficher2 = False
                        for activity in ldap_enum_activities:
                            if activity.results:
                                afficher2 = True
                                break

                        if afficher1 == True and afficher2 == True:
                            attack_techniques["1003.006"] = {
                                "name": "OS Credential Dumping: DCSync",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-dcsync",
                                "description": "Using a technique called DCSync, adversaries may exploit the application programming interface (API) of a Windows Domain Controller to simulate the replication process from a remote domain controller, aiming to gain unauthorized access to credentials and other sensitive information.",
                            }

                        # traiter pour voir si on affiche ou non le golden ticket
                        lsass_activities = Activity.objects.filter(
                            Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
                                type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                            workspace_id=session["workspace"], results__isnull=False)

                        afficher1 = False
                        for activity in lsass_activities:
                            if activity.results and "traitement" in activity.results:
                                if activity.results["traitement"]:
                                    afficher1 = True
                                    break

                        ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration",
                                                                       user_id=request.user.id,
                                                                       workspace_id=session["workspace"],
                                                                       results__isnull=False)
                        afficher2 = False
                        for activity in ldap_enum_activities:
                            if activity.results:
                                afficher2 = True
                                break

                        dcsync_activities = Activity.objects.filter(type="T1003.006 - Dcsync",
                                                                    user_id=request.user.id,
                                                                    workspace_id=session["workspace"],
                                                                    results__isnull=False)

                        afficher3 = False
                        for activity in dcsync_activities:
                            if activity.results and "creds" in activity.results:
                                if len(activity.results["creds"]) > 0:
                                    afficher3 = True
                                    break
                        if afficher1 == True and afficher2 == True and afficher3 == True:
                            attack_techniques["T1558.001"] = {
                                "name": "Forge Kerberos Tickets: Golden Ticket",
                                "tactic": request.GET.get("step"),
                                "url": "attacks-golden_ticket",
                                "description": "Having possession of the KRBTGT account password hash empowers adversaries to fabricate Kerberos ticket-granting tickets (TGT), commonly referred to as golden tickets. These golden tickets provide adversaries with the ability to produce authentication credentials for any account within the Active Directory system."
                            }

                        # retourner les ttps
                        contexte["techniques"] = attack_techniques

                    elif request.GET.get("step") == "discovery":

                        attack_techniques["T1078.002"] = {
                            "name": "Ldap enumeration",
                            "tactic": request.GET.get("step"),
                            "url": "attacks-ldap_enum",
                            "description": "retrieve a list of accounts in a target environment",
                        }

                        attack_techniques["T1078"] = {
                            "name": "SMB enumeration",
                            "tactic": request.GET.get("step"),
                            "url": "attacks-smb_enum",
                            "description": "Process in which we enumerate the host or target system for different information",
                        }

                        # retourner les ttps
                        contexte["techniques"] = attack_techniques






                    else:

                        messages.error(request, "Vous devez d'abord spécifier la session")

        return render(request, 'attacks.html', contexte)
    else:
        messages.error(request, "You must select a workspace first")
        return render(request, 'attacks.html', {})


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_network_scan(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = Network_scan_form(request.POST)
        # check whether it's valid:
        if form.is_valid():
            network_scan_name = form.cleaned_data["network_scan_name"]
            network_scan_ip = form.cleaned_data["network_scan_ip"]
            network_scan_ports = form.cleaned_data["network_scan_ports"]
            network_scan_type = form.cleaned_data["network_scan_type"]
            service_version = form.cleaned_data["service_version"]
            os_discovery = form.cleaned_data["os_discovery"]

            # ici on va enregistrer ce qu'il faut dans la base de données
            session = request.session
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="Network scan", name=network_scan_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']
            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            # On lance le scan en arrière plan :
            print(network_scan_type)
            subprocess.Popen(["python", "My_app/scripts/network_scan.py", "--name", network_scan_name, "--activity_id", str(max_id),
                              "--address", network_scan_ip, "--port", network_scan_ports, "--scan_type", network_scan_type,
                              "--service_version", str(service_version), "--os", str(os_discovery)
                              ])

            print("formulaire valide")
            return redirect("My_app-attacks")



    else:
        form = Network_scan_form()

    contexte = {
        'form': form
    }

    return render(request, 'attacks/attacks_network_scan.html', contexte)


#-----------------------------------------------------------------------------------------------------------------------

@login_required
def attacks_vuln_scan(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    # On recupere les address ip:
    session = request.session
    activities = Activity.objects.filter(user_id=request.user.id, type="Network scan", workspace_id=session["workspace"], results__isnull=False)
    list_ip_address = []
    for activity in activities:
        activity_result = activity.results
        for key, value in activity_result.items():
            exist = False
            for ip_address in list_ip_address:

                if key in ip_address:
                    exist = True
                    break
            if exist == False:
                list_ip_address.append((key, key))

    # Tranformer la liste en tuple :
    tuple_ip_address = tuple(list_ip_address)

    if request.method == 'POST':
        form = Vuln_scan_form(request.POST, choices=tuple_ip_address)
        print(form['ip_address'].value())
        print(form['ip_address2'].value())
        # check if form is valid :
        if form.is_valid():
            #enregistrer au niveau de la BDD
            vuln_scan_name = form.cleaned_data['vuln_scan_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="vuln scan",
                                    name=vuln_scan_name,
                                    begin_date=datetime.now())

            #commencer le scan de vulnerabilité

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            vuln_scan_ip = None #----- ajouté
            if form.cleaned_data["ip_address"]: #-----ajouté
                vuln_scan_ip = form.cleaned_data["ip_address"]
            else: #----- ajouté
                vuln_scan_ip = form.cleaned_data["ip_address2"]
            # On lance le scan en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/vuln_scanner2.py", "--activity_id", str(max_id),
                 "--ip", str(vuln_scan_ip),
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-vuln_scan')

    else:
        form = Vuln_scan_form(choices=tuple_ip_address)

        contexte = {
            'form' : form
        }
        return render(request, 'attacks/attacks_vuln_scan.html', contexte)



#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_ldap_enum(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    # On recupere les address ip:
    session = request.session
    activities = Activity.objects.filter(user_id=request.user.id, type="Network scan",
                                         workspace_id=session["workspace"], results__isnull=False)
    list_ip_address = []
    for activity in activities:
        activity_result = activity.results
        for key, value in activity_result.items():
            exist = False
            for ip_address in list_ip_address:

                if key in ip_address:
                    exist = True
                    break
            if exist == False:
                list_ip_address.append((key, key))
    # Tranformer la liste en tuple :
    tuple_ip_address = tuple(list_ip_address)

    if request.method == 'POST':
        form = Ldap_enum_form(request.POST, choices=tuple_ip_address)
        print(form['ip_address'].value())
        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            ldap_enum_name = form.cleaned_data['ldap_enum_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="Ldap enumeration",
                                    name=ldap_enum_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            ldap_enum_ip = None
            if form.cleaned_data["ip_address"]:
                ldap_enum_ip = form.cleaned_data["ip_address"]
            else:
                ldap_enum_ip = form.cleaned_data["ip_address2"]

            ldap_enum_user = form.cleaned_data["username"]
            ldap_enum_password = form.cleaned_data["password"]
            ldap_enum_domain_name = form.cleaned_data["domain_name"]
            # On lance l'enumeration en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/enum-ldap.py", "--activity_id", str(max_id),
                 "--address", str(ldap_enum_ip), "--username", ldap_enum_user, "--password", ldap_enum_password,
                 "--domain_name", ldap_enum_domain_name,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-ldap_enum')

    else:

        form = Ldap_enum_form(choices=tuple_ip_address)
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_ldap_enum.html', contexte)

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_smb_enum(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    # On recupere les address ip:
    session = request.session
    activities = Activity.objects.filter(user_id=request.user.id, type="Network scan",
                                         workspace_id=session["workspace"], results__isnull=False)
    list_ip_address = []
    for activity in activities:
        activity_result = activity.results
        for key, value in activity_result.items():
            exist = False
            for ip_address in list_ip_address:

                if key in ip_address:#
                    exist = True
                    break
            if exist == False:
                list_ip_address.append((key, key))

    # Tranformer la liste en tuple :
    tuple_ip_address = tuple(list_ip_address)

    if request.method == 'POST':
        form = Smb_enum_form(request.POST, choices=tuple_ip_address)
        print(form['ip_address'].value())
        print(form["ip_address2"].value())
        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            smb_enum_name = form.cleaned_data['smb_enum_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="SMB enumeration",
                                    name=smb_enum_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            smb_enum_ip = None
            if form.cleaned_data["ip_address"]:
                smb_enum_ip = form.cleaned_data["ip_address"]
            else:
                smb_enum_ip = form.cleaned_data["ip_address2"]

            # On lance l'enumeration en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/enum-smb.py", "--activity_id", str(max_id),
                 "--address", str(smb_enum_ip),
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-smb_enum')

    else:

        form = Smb_enum_form(choices=tuple_ip_address)
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_smb_enum.html', contexte)



#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_exploitation(request):

    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    # Recuperer les nom des activité vuln scan et leurs IDs
    session = request.session
    vuln_scans = Activity.objects.filter(user_id=request.user.id, type="vuln scan",
                                         workspace_id=session["workspace"], results__isnull=False)

    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario ----------

    if "scenario_name" in session:
        if len(vuln_scans) == 0:
            messages.error(request,
                           "Exploitation not possible : the scenario was stopped because there is no vulnerability scan activity that has been performed")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})
    #--------------------












    vuln_scans_name = []
    for activity in vuln_scans:
        vuln_scans_name.append((activity.id, activity.name))

    # si c'est une requete POST alors on affiche les noms des vulnérabilités trouvés dans l'activité
    if request.method == "POST":
        form = Exploitation_form(request.POST, choices=vuln_scans_name) # le nom doit etre unique ( a changer dans la BDD ) !!!!!!!!!!!!!
        if form.is_valid():
            activity_id = form.cleaned_data["imported_vuln"]
            # on doit recuperer les resultat de cette activité :
            activity = Activity.objects.get(id=activity_id)
            vulns = {}  # ce dictionnaire va contenir a la fin pour chaque vulnerabilité sa liste de cve
            # parcourir les vulnérabilités:
            for vuln in activity.results["get_reports_response"]["report"]["report"]["results"]["result"]:
                # pour chaque vulnerbilité on va obtenir sa liste de CVE

                if vuln['nvt'].get('refs') is not None:
                    if isinstance(vuln['nvt']["refs"]["ref"], dict) and vuln['nvt']['refs']['ref'].get(
                            "@type") is not None:
                        if vuln['nvt']['refs']['ref']['@type'] == "cve":
                            list_ref = []
                            cve_id = vuln['nvt']['refs']['ref']["@id"]

                            if cve_id is not None:
                                list_ref.append(cve_id)
                                target = vuln['host']["#text"]
                                vulns[vuln["name"]] = {
                                    "refs": list_ref,
                                    "ip": target,
                                }

                    else:
                        list_ref = []
                        for reference in vuln["nvt"]["refs"]["ref"]:
                            if reference.get("@type") is not None:
                                if reference.get("@type") == "cve":
                                    cve_id = reference["@id"]
                                    if cve_id is not None:
                                        list_ref.append(cve_id)

                        # dans le cas ou il y'a au moin un cve dans les refs de la vuln :
                        if len(list_ref) != 0:
                            target = vuln['host']["#text"]
                            vulns[vuln["name"]] = {
                                "refs": list_ref,
                                "ip": target,
                                "vuln_name": quote(vuln["name"]),
                            }

        return render(request, "attacks/attacks_exploitation.html", {"vulns": vulns})
    else:

        if request.GET.get('cve'):
            client = MsfRpcClient('anis', ssl=True)
            target = request.GET.get('target')
            cves = request.GET.get('cve').split('|')
            cves_search_results = []
            for cve in cves:
                filter = "cve:" + str(cve[4:]) + " type:exploit"
                cve_search_results = client.call('module.search', [filter])
                if len(cve_search_results) != 0:
                    for module in cve_search_results:
                        if module not in cves_search_results:
                            cves_search_results.append(module)
                #cves_search_results = cves_search_results + cve_search_results

            exploitation = {
                "modules": cves_search_results,
                "target": target,
                "vuln_name" : quote(request.GET.get("vuln")),
            }

            return render(request, "attacks/attacks_exploitation.html", {"exploitation": exploitation})

        elif request.GET.get('exploit'):
            # dans le cas ou on a choisis un exploit on affiche une liste de payload :
            target = request.GET.get('target')
            char_exploit = request.GET.get('exploit')
            prepared_exploit = char_exploit[8:]
            client = MsfRpcClient('anis', ssl=True)

            exploit = client.modules.use('exploit', prepared_exploit)
            payloads = exploit.payloads
            banned_chars = ["/vncinject/", "powershell", "/custom", "/peinject/", "/upexec/", "pingback", "/exec", "/messagebox"]
            allowed_chars = ["/shell", "/meterpreter", '/cmd/unix']
            filtred_payloads = []
            for payload in payloads:
                test = False
                test2 = False
                for allowed_char in allowed_chars:
                    if payload.find(allowed_char) != -1:
                        for banned_char in banned_chars:
                            if payload.find(banned_char) != -1:
                                test = True
                                break
                        test2 = True
                        break

                if test == False and test2 == True:
                    filtred_payloads.append(payload)


            contexte = {
                "payloads": filtred_payloads,
                "exploit": prepared_exploit,
                "target": target,
                "vuln_name": quote(request.GET.get("vuln"))
            }
            return render(request, "attacks/attacks_exploitation.html", contexte)


        elif request.GET.get("payload"):
            exploit = request.GET.get("exploitation")
            payload = request.GET.get("payload")
            rhost = request.GET.get("target")
            vuln_name = request.GET.get("vuln")

            # Recuperer le nombre d'exploitation deja effectué Pour avoir un nom different pour chaque exploitation:
            count_exploitations = Activity.objects.filter(type="Exploitation").count()
            print("count_exploitation = " + str(count_exploitations))
            activity_name = "Exploitation N°" + str(count_exploitations + 1)
            # ici on va enregistrer ce qu'il faut dans la base de données
            session = request.session
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="Exploitation",
                                    name=activity_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                print("loooooooooooooooool")
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            # lancer le programme de l'exploitation
            subprocess.Popen(
                ["python", "My_app/scripts/exploitation.py", "--exploit", exploit, "--activity_id", str(max_id),
                 "--Raddress", rhost, "--payload", payload, "--vuln_name", vuln_name,
                 ])

            return redirect("My_app-activite")

        else:
            # si c'est une requete GET sans parametres on lui affiche la liste des scans de vulnerabilité qu'il a éffectué,
            # Pour qu'il choisis et il importe un scan


            form = Exploitation_form(choices=vuln_scans_name)

            contexte = {
                "form": form,
            }
            return render(request, "attacks/attacks_exploitation.html", contexte)

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_post_exp(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    contexte = {
    }
    if request.method == "POST":
        #Obtenir les attribut de la requete POST
        tactic = request.POST.get("tactic")
        technique = request.POST.get("technique")
        procedure = request.POST.get("procedure")
        attack_session_uuid = request.POST.get("session_uuid")
        activity_name = request.POST.get("activity_name")

        # Obtenir la version du system: (j'aurais besoin de l'os pour afficher les traces par la suite donc je dois enregistrer l'os pour chaque technique utilisé)
        exploitations = Activity.objects.filter(Q(type="Exploitation") | Q(type="Port listener"))
        session_os = None
        target_address = None
        for exp in exploitations:
            exp_result = exp.results
            if exp_result != None:
                if "session_uuid" in exp_result:
                    if exp_result["session_uuid"] == attack_session_uuid:
                        if "session_os" in exp_result:
                            session_os = exp_result["session_os"]
                            target_address = exp_result["target_ip"]
                        break

        #Ouvrture du fichier .yaml qui représente la technique pour modifier les valeurs des input
        origin_dir_path = os.path.abspath(os.getcwd())

        technique_directory = os.path.join("My_app/scripts/atomics", tactic, technique)

        os.chdir(technique_directory)

        # Récuperer tout les fichiers qui se terminent par .yaml
        yaml_files = glob.glob("*yaml")

        # Ouvre le fichier YAML en mode lecture
        with open(yaml_files[0], 'r+') as file:
            # Charge le contenu du fichier YAML
            yaml_data = yaml.safe_load(file)

            # Modifier les input_arguments de la procedure
            for atomic in range(len(yaml_data["atomic_tests"])):
                if yaml_data["atomic_tests"][atomic]["name"] == procedure:
                    if "input_arguments" in yaml_data["atomic_tests"][atomic]:
                        for key, value in request.POST.items():
                            if key in yaml_data["atomic_tests"][atomic]["input_arguments"]:
                                yaml_data["atomic_tests"][atomic]["input_arguments"][key]["default"] = value

                    break

            # Se positionner au début du fichier
            file.seek(0)

            # Écrire les données modifiées dans le fichier
            yaml.dump(yaml_data, file, default_flow_style=False)

            # Tronquer le fichier après la fin des données écrites
            file.truncate()

        # revenir vers le repertoire d'origine
        os.chdir(origin_dir_path)

        # ajouter une activity dans la base de données
        session = request.session
        Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type=technique + "-" + procedure,
                                name=activity_name,
                                begin_date=datetime.now()) # je dois changer le name et le begin_date !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

        # Recuperer le plus grand id de la table Activity :
        max_id = Activity.objects.aggregate(Max('id'))['id__max']

        # Dans le cas ou un scenario est en cours :
        session = request.session
        if "scenario_name" in session:
            session["current_scenario_step_status"] = "running"
            session["current_step_id"] = max_id
            session.save()

        print("session_os = " + session_os)

        # executer un processus avec subprocess qui lance la commande
        subprocess.Popen(
            ["python", "My_app/scripts/post_exp.py", "--tactic", tactic, "--technique", technique,
             "--procedure", procedure, "--session_uuid", attack_session_uuid, "--activity_id", str(max_id), "--session_os", session_os,
             "--target_address", target_address,
             ])



        return redirect("My_app-activite")



    elif request.method == "GET":
        if "technique" in request.GET and "procedure" not in request.GET:

            origin_dir_path = os.path.abspath(os.getcwd())

            technique = request.GET.get("technique")
            tactic = request.GET.get("tactic")
            attack_session_uuid = request.GET.get("uuid")

            technique_directory = os.path.join("My_app/scripts/atomics", tactic, technique)

            # Récupère le chemin absolu du répertoire courant
            os.chdir(technique_directory)
            dir_path = os.path.abspath(os.getcwd())

            attack_techniques = {}  # Dictionnaire qui stocke toutes les techniques

            # Récuperer tout les fichiers qui se terminent par .yaml
            yaml_files = glob.glob("*yaml")

            # Ouvre le fichier YAML en mode lecture
            with open(yaml_files[0], 'r') as file:
                # Charge le contenu du fichier YAML
                yaml_data = yaml.safe_load(file)
            # Accède aux différents champ du fichier
            attack_technique = yaml_data['attack_technique']
            display_name = yaml_data['display_name']
            atomic_tests = yaml_data['atomic_tests']

            # je recupere les information concernant la session_uuid:
            session = request.session
            activities = Activity.objects.filter(Q(type="Exploitation") | Q(type="Port listener"), user_id=request.user.id,
                                                 workspace_id=session["workspace"], results__isnull=False)

            attack_session_os = None
            attack_session_user = None
            user_groups = None
            payload_type = None
            for activity in activities:
                if "session_uuid" in activity.results:
                    if activity.results["session_uuid"] == attack_session_uuid:
                        attack_session_os = activity.results["session_os"]
                        attack_session_user = activity.results["session_user"]
                        user_groups = activity.results["user_groups"]
                        payload_type = activity.results["payload_type"]
                        break

            # parcourir les procédures disponible dans le fichier .yaml
            procedures = {}
            for atomic_test in atomic_tests:
                satisfait = False
                if attack_session_os in atomic_test["supported_platforms"]:
                    if "elevation_required" not in atomic_test["executor"]:
                        satisfait = True
                    else:
                        if atomic_test["executor"]["elevation_required"] == "false":
                            satisfait = True
                        else:
                        #"------------------------------------------------"
                            if "root" in attack_session_user or r"autorite nt\sys" in attack_session_user:  # si l'user est root (represente root dans linux+macos) et system dans windows)
                                satisfait = True
                            elif attack_session_os == "windows":  # sinon si on est sur windows on vérifie si l'user appartient au groupe admin
                                if "Administrateurs" in user_groups or "Administrators" in user_groups:
                                    satisfait = True
                            elif attack_session_os == "linux":
                                if "root" in user_groups:
                                    satisfait = True
                            elif attack_session_os == "macos":
                                if "wheel" in user_groups:
                                    satisfait = True

                if payload_type != "meterpreter":
                    executor_name = atomic_test["executor"]["name"]
                    if executor_name == "powershell":
                        satisfait = False


                if satisfait == True:
                    description = "" #
                    if "description" in atomic_test: #
                        description = atomic_test["description"] #

                    procedures[atomic_test["name"]] = {
                        "name": quote(atomic_test["name"]),
                        "description": description, #
                    }

            # retourner au répértoire d'origine
            os.chdir(origin_dir_path)
            contexte = {
                "procedures": procedures,
                "tactic": tactic,
                "technique": technique,
                "session_uuid": attack_session_uuid
            }

        elif "procedure" in request.GET:
            origin_dir_path = os.path.abspath(os.getcwd())

            technique = request.GET.get("technique")
            tactic = request.GET.get("tactic")
            procedure = request.GET.get("procedure")
            attack_session_uuid = request.GET.get("uuid")
            print(request.GET)
            print(tactic)
            print(technique)

            technique_directory = os.path.join("My_app/scripts/atomics", tactic, technique)
            os.chdir(technique_directory)

            # Récuperer tout les fichiers qui se terminent par .yaml
            yaml_files = glob.glob("*yaml")

            # Ouvre le fichier YAML en mode lecture
            with open(yaml_files[0], 'r') as file:
                # Charge le contenu du fichier YAML
                yaml_data = yaml.safe_load(file)


            # Accède aux différents champ du fichier
            attack_technique = yaml_data['attack_technique']
            display_name = yaml_data['display_name']
            atomic_tests = yaml_data['atomic_tests']

            # revenir au repertoire d'origine
            os.chdir(origin_dir_path)

            # -------------------Partie traitement des dependances pour voir si on peut executer uune technique de post exp dans le scenario ---------------------


            # dans le cas ou on est dans un scenario:
            session = request.session
            if "scenario_name" in session:
                activities = Activity.objects.filter(Q(type="Exploitation") | Q(type="Port listener"),
                                                     user_id=request.user.id,
                                                     workspace_id=session["workspace"], results__isnull=False)

                attack_session_os = None
                attack_session_user = None
                user_groups = None
                payload_type = None
                for activity in activities:
                    if "session_uuid" in activity.results:
                        if activity.results["session_uuid"] == attack_session_uuid:
                            attack_session_os = activity.results["session_os"]
                            attack_session_user = activity.results["session_user"]
                            user_groups = activity.results["user_groups"]
                            payload_type = activity.results["payload_type"]
                            break

                # parcourir les procédures disponible dans le fichier .yaml
                procedures = {}
                for atomic_test in atomic_tests:
                    satisfait = False
                    if attack_session_os in atomic_test["supported_platforms"]:
                        if "elevation_required" not in atomic_test["executor"]:
                            satisfait = True
                        else:
                            if atomic_test["executor"]["elevation_required"] == "false":
                                satisfait = True
                            else:
                                # "------------------------------------------------"
                                if "root" in attack_session_user or r"autorite nt\sys" in attack_session_user:  # si l'user est root (represente root dans linux+macos) et system dans windows)
                                    satisfait = True
                                elif attack_session_os == "windows":  # sinon si on est sur windows on vérifie si l'user appartient au groupe admin
                                    if "Administrateurs" in user_groups or "Administrators" in user_groups:
                                        satisfait = True
                                elif attack_session_os == "linux":
                                    if "root" in user_groups:
                                        satisfait = True
                                elif attack_session_os == "macos":
                                    if "wheel" in user_groups:
                                        satisfait = True

                    if payload_type != "meterpreter":
                        executor_name = atomic_test["executor"]["name"]
                        if executor_name == "powershell":
                            satisfait = False

                    if satisfait == True:
                        description = ""  #
                        if "description" in atomic_test:  #
                            description = atomic_test["description"]  #

                        procedures[atomic_test["name"]] = {
                            "name": quote(atomic_test["name"]),
                            "description": description,  #
                        }

                exist = False
                for key, val in procedures.items():
                    if key == procedure:
                        exist = True
                        break

                procedures = {}

                if exist == False:
                    messages.error(request,
                                   "the scenario was stopped because the context of the current session does not allow you to perform the post exploitation technique choosed")
                    del session["scenario_name"]
                    del session["scenario_steps"]
                    del session["scenario_steps_length"]
                    del session["current_scenario_step"]
                    del session["current_scenario_step_status"]
                    session.save()
                    return render(request, 'attacks.html', {})














            #------------------------------------- Fin de la partie traitement de dependance de la fonctionnalité scénario ----------------------














            # Créer un dictionnaire qui va contenir tout les input
            dynamic_fields = {}
            # Parcourir les tests atomics a la recherche de la procédure séléctionnée
            for atomic_test in atomic_tests:
                if atomic_test["name"] == procedure:
                    # On vérifie si la procédure doit contenir des données que l'utilisateurs doit introduire
                    if "input_arguments" in atomic_test:
                        for input_name, input_info in atomic_test["input_arguments"].items():
                            dynamic_field = forms.CharField(required=True,
                                                             initial=input_info["default"],
                                                             max_length=100,
                                                            label=input_name,
                                                             widget=forms.TextInput(attrs=
                                                             {
                                                                 'class': 'input',
                                                                 'style': 'width: 30vw',

                                                             }
                                                             ))
                            dynamic_fields[input_name] = dynamic_field
                    break

            # On crée également des champs cachées qu'on aurais besoin par la suite dans le POST pour savoir quelle technique executer

            # On crée un champ cachée pour la tactic
            dynamic_field = forms.CharField(required=True,
                                            initial=tactic,
                                            max_length=100,
                                            widget=forms.HiddenInput(attrs=
                                            {
                                                'class': 'input',
                                                'style': 'width: 30vw',

                                            }
                                            ))
            dynamic_fields["tactic"] = dynamic_field

            # On crée un champ cachée pour la technique
            dynamic_field = forms.CharField(required=True,
                                            initial=technique,
                                            max_length=100,
                                            widget=forms.HiddenInput(attrs=
                                            {
                                                'class': 'input',
                                                'style': 'width: 30vw',

                                            }
                                            ))
            dynamic_fields["technique"] = dynamic_field

            # On crée un champ cachée pour la tactic
            dynamic_field = forms.CharField(required=True,
                                            initial=procedure,
                                            max_length=100,
                                            widget=forms.HiddenInput(attrs=
                                            {
                                                'class': 'input',
                                                'style': 'width: 30vw',

                                            }
                                            ))
            dynamic_fields["procedure"] = dynamic_field

            # On crée un champ cachée pour la tactic
            dynamic_field = forms.CharField(required=True,
                                            initial=attack_session_uuid,
                                            max_length=100,
                                            widget=forms.HiddenInput(attrs=
                                            {
                                                'class': 'input',
                                                'style': 'width: 30vw',

                                            }
                                            ))
            dynamic_fields["session_uuid"] = dynamic_field

            # Créer un formulaire dynamique avec des champs dynamiques
            dynamic_form = Post_exp_form(dynamic_fields=dynamic_fields)

            # mettre a jour le contexte
            contexte["form"] = dynamic_form


        return render(request, "attacks/attacks_post_exp.html", contexte)

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_password_cracking(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    # On recupere les address ip:
    session = request.session

    #----- rajouté 22-05-23 ----------------

    # Recuperer les nom des activité de dumps
    dump_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll") | Q(type="T1003.002-Dump-SAM-With-Mimikatz") | Q(type="T1003.005-Cached Credential Dump via Mimikatz"),user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
    hashs = []
    for activity in dump_activities:
        if activity.type == "T1003.001-Dump LSASS.exe Memory using ProcDump" or activity.type == "T1003.001-Dump LSASS.exe Memory using comsvcs.dll":
            if "traitement" in activity.results:
                if activity.results["traitement"]:
                    traitement = activity.results["traitement"]
                    for sid, dumps in traitement.items():
                        if dumps["ntlm_hash"]:
                            exist = False
                            for hash_tuple in hashs:
                                if dumps["ntlm_hash"] in hash_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                hashs.append(("nt-" + dumps["ntlm_hash"], dumps["ntlm_hash"]))
                        if dumps["lm_hash"]:
                            exist = False
                            for hash_tuple in hashs:
                                if dumps["lm_hash"] in hash_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                hashs.append(("lm-" + dumps["lm_hash"], dumps["lm_hash"]))

        elif activity.type == "T1003.002-Dump-SAM-With-Mimikatz":
            if "traitement" in activity.results:
                if activity.results["traitement"]:
                    traitement = activity.results["traitement"]
                    for rid, dumps in traitement.items():
                        if dumps["Hash_NTLM"]:
                            exist = False
                            for hash_tuple in hashs:
                                if dumps["Hash_NTLM"] in hash_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                hashs.append(("nt-" + dumps["Hash_NTLM"], dumps["Hash_NTLM"]))

        elif activity.type == "T1003.005-Cached Credential Dump via Mimikatz":
            if "traitement" in activity.results:
                if activity.results["traitement"]:
                    traitement = activity.results["traitement"]
                    for rid, dumps in traitement.items():
                        if dumps["MsCacheV2"]:
                            exist = False
                            user = dumps["User"]
                            if "\\" in user:
                                user = user.split("\\")[-1]
                            my_hash = user + ":" + dumps["MsCacheV2"]
                            for hash_tuple in hashs:
                                if my_hash in hash_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                hashs.append(("mscash2-" + my_hash, my_hash))




    # recuperer les activités de kerberoasting


    kerberoasting_activities = Activity.objects.filter(type="T1558.003 - Kerberoasting",user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
    if len(kerberoasting_activities) > 0:
        for activity in kerberoasting_activities:
            if activity.results and "services" in activity.results:
                services = activity.results["services"]
                if len(services) > 0:
                    for service in services:
                        if "SPN" in service and "service_compte_hash" in service:
                            if service["SPN"] and service["service_compte_hash"]:
                                my_tgs = "krb5tgs-" + service["SPN"] + "_" + service["computer_service"] + ":" + service["service_compte_hash"]
                                affichage = "From kerberoasting - SPN : " + str(service["SPN"]) + " - Service account : " + str(service["computer_service"])
                                exist = False
                                for tgs_ticket in hashs:
                                    if affichage in tgs_ticket:
                                        exist = True
                                        break

                                if exist == False:
                                    hashs.append((my_tgs, affichage))

    print(hashs)

    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario
    if "scenario_name" in session:
        if len(hashs) == 0:
            messages.error(request,
                           "the scenario was stopped because the information needed to execute password cracking are not available")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})













    #--------------------------------------


    if request.method == 'POST':
        form = Password_cracking_form(request.POST, choices=hashs)

        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            password_cracking_name = form.cleaned_data['password_cracking_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="T1110.002 - Password cracking",
                                    name=password_cracking_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            hash_type = None
            hash_value = None
            if form.cleaned_data["hash_value"]:
                hash_type = form.cleaned_data["hash_type"]
                hash_value = form.cleaned_data["hash_value"]
            elif form.cleaned_data["hash_choices"]:
                hash_choice = form.cleaned_data["hash_choices"]
                hash_choice = hash_choice.split("-")
                hash_value = hash_choice[1]
                hash_type = hash_choice[0]


            wordlist_path = form.cleaned_data["wordlist_path"]

            print("hash selected : " + hash_value + " of type : " + hash_type)

            # On lance l'enumeration en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/password_cracking.py", "--activity_id", str(max_id),
                 "--hash_value", hash_value, "--hash_type", hash_type, "--wordlist_path", wordlist_path,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-password_cracking')

    else:

        form = Password_cracking_form(choices=hashs)
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_password_cracking.html', contexte)


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_pth(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    session = request.session
    # recuperer les hashs dumpé
    dump_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll") | Q(type="T1003.002-Dump-SAM-With-Mimikatz"),user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
    hashs = []
    for activity in dump_activities:
        if activity.type == "T1003.001-Dump LSASS.exe Memory using ProcDump" or activity.type == "T1003.001-Dump LSASS.exe Memory using comsvcs.dll":
            if "traitement" in activity.results:
                if activity.results["traitement"]:
                    traitement = activity.results["traitement"]
                    for sid, dumps in traitement.items():
                        if dumps["ntlm_hash"]:
                            my_hash = dumps["username"] + ":" + dumps["ntlm_hash"]
                            domain_name = dumps["domain_name"]
                            my_hash_domain = domain_name + "-" + my_hash
                            my_hash_local = "local-" + my_hash
                            exist = False
                            for hash_tuple in hashs:
                                if my_hash_domain in hash_tuple or my_hash_local in hash_tuple:
                                    exist = True
                                    break
                            if exist == False:

                                attack_activities = Activity.objects.filter(Q(type="Exploitation") | Q(type="Port listener"), user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)

                                for attack_activity in attack_activities:
                                    if attack_activity.results:

                                        if "session_uuid" in attack_activity.results and "attack_session_uuid" in session and "hostname" in attack_activity.results:
                                            #print("session_uuid = " + attack_activity.results["session_uuid"] + " ;; attack_session_uuid = " + session["attack_session_uuid"])

                                            if "session uuid:" + attack_activity.results["session_uuid"] == request.session["attack_session_uuid"]:
                                                hostname = attack_activity.results["hostname"]
                                                print("test")
                                                if domain_name.lower() not in hostname.lower():
                                                    hashs.append((domain_name + "-" + dumps["username"] + ":" + dumps["ntlm_hash"], domain_name + "-" + dumps["username"] + ":" + dumps["ntlm_hash"]))
                                                else:
                                                    hashs.append(("local-" + dumps["username"] + ":" + dumps["ntlm_hash"], "local-" + dumps["username"] + ":" + dumps["ntlm_hash"]))
                                                break

        if activity.type == "T1003.002-Dump-SAM-With-Mimikatz":
            if "traitement" in activity.results:
                if activity.results["traitement"]:
                    traitement = activity.results["traitement"]
                    for rid, dumps in traitement.items():
                        if dumps["Hash_NTLM"]:
                            my_hash = "local-" + dumps["User"] + ":" + dumps["Hash_NTLM"]

                            exist = False
                            for hash_tuple in hashs:
                                if my_hash in hash_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                hashs.append(("local-" + dumps["User"] + ":" + dumps["Hash_NTLM"], "local-" + dumps["User"] + ":" + dumps["Hash_NTLM"]))





    print(hashs)

    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario
    if "scenario_name" in session:
        if len(hashs) == 0:
            messages.error(request,
                           "the scenario was stopped because the informations needed to execute a pass the hash attack are not available")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})













    #----

    if request.method == 'POST':
        form = Pth_form(request.POST, choices=hashs)

        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            pth_name = form.cleaned_data['pth_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="T1550.002 - Pass the hash",
                                    name=pth_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            username = None
            hash_value = None
            domain = None
            if form.cleaned_data["hash_value"]:
                hash_value = form.cleaned_data["hash_value"]
                username = form.cleaned_data["username"]
                if form.cleaned_data["domain"]:
                    domain = form.cleaned_data["domain"]
                else:
                    domain = ""
            elif form.cleaned_data["hash_choices"]:
                ## code pour gérer le choix a partir de la bdd
                hash_choices = form.cleaned_data["hash_choices"]
                domain_or_local = hash_choices.split("-")[0]
                creds = hash_choices.split("-")[1]
                username = creds.split(":")[0]
                hash_value = creds.split(":")[1]
                if domain_or_local == "local":
                    domain = ""
                else:
                    domain = domain_or_local



            print("Username : " + username)
            print("Hash value : " + hash_value)
            print("domain : " + domain)

            # On lance l'enumeration en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/pth.py", "--activity_id", str(max_id),
                 "--ntlm_hash", hash_value, "--username", username, "--domain_name", domain,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-pth')

    else:

        form = Pth_form(choices=hashs)
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_pth.html', contexte)


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_dcsync(request):

    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    session = request.session

    #- ajouté le 24-05-23 -------------------------------

    #récupérer les dns_host_name des controlleurs de domaines

    domain_controllers_dhn = []
    ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration" ,user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
    if len(ldap_enum_activities) > 0:
        for ldap_activity in ldap_enum_activities:
            if "domain_controllers" in ldap_activity.results:
                if len(ldap_activity.results["domain_controllers"]) > 0:
                    activity_domain_controllers = ldap_activity.results["domain_controllers"]
                    for domain_controller in activity_domain_controllers:
                        if domain_controller["dns_host_name"]:
                            exist = False
                            for dhn in domain_controllers_dhn:
                                if domain_controller["dns_host_name"] in dhn:
                                    exist = True
                                    break
                            if exist == False:
                                domain_controllers_dhn.append((domain_controller["dns_host_name"], domain_controller["dns_host_name"]))

    print(domain_controllers_dhn)

    # Récupérer les comptes (username + hash ntlm) a partir des dump lsass effectué et que le username doit appartenir au admin dans les activité ldap efféctué

    lsass_credentials = []
    lsass_dump_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"),user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)

    if len(lsass_dump_activities) > 0:
        for lsass_dump_activity in lsass_dump_activities:
            if lsass_dump_activity.results["traitement"]:
                traitement = lsass_dump_activity.results["traitement"]
                for sid, dumps in traitement.items():
                    if dumps["ntlm_hash"]:
                        my_hash = dumps["username"] + "-00000000000000000000000000000000:" + dumps["ntlm_hash"]

                        exist = False
                        for lsass_creds_tuple in lsass_credentials:
                            if my_hash in lsass_creds_tuple:
                                exist = True
                                break
                        if exist == False:
                            # verifier si l'user est dans les ldap_enums
                            exist2 = False
                            for ldap_activity in ldap_enum_activities:
                                if "domain_admins" in ldap_activity.results:
                                    if len(ldap_activity.results["domain_admins"]) > 0:
                                        activity_domain_admins = ldap_activity.results["domain_admins"]
                                        for domain_admin in activity_domain_admins:
                                            if domain_admin["name"] == dumps["username"]:
                                                exist2 = True
                                                break
                                        if exist2 == True:
                                            break
                            if exist2 == True:
                                lsass_credentials.append((my_hash, dumps["username"]))

    print(lsass_credentials)

    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario
    if "scenario_name" in session:
        if len(lsass_credentials) == 0 or len(domain_controllers_dhn) == 0:
            messages.error(request,
                           "the scenario was stopped because the information needed to execute DCSync is not available")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})



    #---------------------------------------------------




    if request.method == 'POST':
        form = Dcsync_form(request.POST)
        form.fields['domain_controllers'].choices = domain_controllers_dhn
        form.fields['credentials'].choices = lsass_credentials
        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            dcsync_name = form.cleaned_data['dcsync_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="T1003.006 - Dcsync",
                                    name=dcsync_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            ip_address = ""
            domain = ""
            username = ""
            user_password = ""
            cred_hash = ""

            if form.cleaned_data["username"]:
                ip_address = form.cleaned_data["ip_address"]
                domain = form.cleaned_data["domain"]
                username = form.cleaned_data["username"]
                user_password = form.cleaned_data["password"]

            elif form.cleaned_data["credentials"]:
                ip_address = form.cleaned_data["domain_controllers"]
                info_domain = ip_address.split(".")
                domain = info_domain[1] + "." + info_domain[2]
                username = form.cleaned_data["credentials"].split("-")[0]
                cred_hash = form.cleaned_data["credentials"].split("-")[1]





            print("Username : " + username)
            print("ip address : " + ip_address)
            print("domain name : " + domain)
            print("password : " + user_password)


            # On lance l'enumeration en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/dcsync.py", "--activity_id", str(max_id),
                 "--ip_dc", ip_address, "--username_admin", username, "--domain_name", domain, "--password", user_password, "--lm_nt_hash", cred_hash,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-dcsync')

    else:

        form = Dcsync_form()
        form.fields['domain_controllers'].choices = domain_controllers_dhn
        form.fields['credentials'].choices = lsass_credentials
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_dcsync.html', contexte)


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_golden_ticket(request):

    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    session = request.session

    # récupérer le hash ntlm de krbtgt depuis la bdd :
    dcsync_activities = Activity.objects.filter(type="T1003.006 - Dcsync",user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)

    krbtgt_hash = []
    if len(dcsync_activities) > 0:
        for dcsync_activity in dcsync_activities:
            if dcsync_activity.results["creds"]:
                creds = dcsync_activity.results["creds"]
                for credential in creds:
                    if credential["username"] == "krbtgt" and credential["nt_hash"]:
                        exist = False

                        for hash_tuple in krbtgt_hash:
                            if credential["nt_hash"] in hash_tuple:
                                exist = True

                        if exist == False:
                            krbtgt_hash.append((credential["nt_hash"], "krbtgt-" + credential["nt_hash"]))

    print(krbtgt_hash)

    # Récupération des utilisateur a spoofer (admin + simple users)
    ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration",user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
    domain_users = []
    if len(ldap_enum_activities) > 0:
        for ldap_activity in ldap_enum_activities:
            if "domain_users" in ldap_activity.results:
                if len(ldap_activity.results["domain_users"]) > 0:
                    activity_domain_users = ldap_activity.results["domain_users"]
                    for activity_domain_user in activity_domain_users:
                        if activity_domain_user["name"]:
                            exist = False
                            for domain_user_tuple in domain_users:
                                if activity_domain_user["name"] in domain_user_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                domain_users.append((activity_domain_user["name"], activity_domain_user["name"]))

    print(domain_users)


    # récupérer les sid du domaine ( et peut etre de la machine cible local )

    list_choice_sid = []
    lsass_dump_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
        type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                                                    workspace_id=session["workspace"], results__isnull=False)

    if len(lsass_dump_activities) > 0:
        for lsass_dump_activity in lsass_dump_activities:
            if lsass_dump_activity.results["traitement"]:
                traitement = lsass_dump_activity.results["traitement"]
                for sid, dumps in traitement.items():
                    if dumps["domain_name"]:

                        treated_sid = sid.rsplit("-", 1)[0]
                        exist = False
                        for sid_tuple in list_choice_sid:
                            if treated_sid in sid_tuple:
                                exist = True
                                break
                        if exist == False:
                            list_choice_sid.append((treated_sid, dumps["domain_name"] + "-" + treated_sid))

    print(list_choice_sid)

    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario
    if "scenario_name" in session:
        if len(list_choice_sid) == 0 or len(domain_users) == 0 or len(krbtgt_hash) == 0:
            messages.error(request,
                           "the scenario was stopped because the information needed to forge a golden ticket is not available")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})











    #----------




    if request.method == 'POST':
        form = Golden_ticket_form(request.POST)
        form.fields['hash_krbtgt_choice'].choices = krbtgt_hash
        form.fields['domain_sid_choice'].choices = list_choice_sid
        form.fields['spoofed_username_choice'].choices = domain_users

        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            golden_ticket_name = form.cleaned_data['golden_ticket_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="T1558.001 - Golden ticket",
                                    name=golden_ticket_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()



            hash_krbtgt = ""
            domain = ""
            domain_sid = ""
            spoofed_username = ""

            if form.cleaned_data["hash_krbtgt"]:
                hash_krbtgt = form.cleaned_data["hash_krbtgt"]
                domain = form.cleaned_data["domain"]
                domain_sid = form.cleaned_data["domain_sid"]
                spoofed_username = form.cleaned_data["spoofed_username"]

            elif form.cleaned_data["hash_krbtgt_choice"]:
                hash_krbtgt = form.cleaned_data["hash_krbtgt_choice"]
                domain = form.cleaned_data["domain"]
                domain_sid = form.cleaned_data["domain_sid_choice"]
                spoofed_username = form.cleaned_data["spoofed_username_choice"]


            print("hash krbtgt : " + hash_krbtgt)
            print("domain name : " + domain)
            print("domain sid : " + domain_sid)
            print("spoofed username : " + spoofed_username)


            # On lance la generation en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/golden-ticket-attack.py", "--activity_id", str(max_id),
                 "--nthash_krbtgt", hash_krbtgt, "--domain_name", domain, "--domain_sid", domain_sid, "--username", spoofed_username,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-golden_ticket')

    else:

        form = Golden_ticket_form()
        form.fields['hash_krbtgt_choice'].choices = krbtgt_hash
        form.fields['domain_sid_choice'].choices = list_choice_sid
        form.fields['spoofed_username_choice'].choices = domain_users
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_golden_ticket.html', contexte)



#-----------------------------------------------------------------------------------------------------------------------
login_required
def attacks_ptt(request):

    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    
    session = request.session


    # Récuperation depuis la bdd :

    # recuperation d'abord des chemin de chaque tgt

    golden_activities = Activity.objects.filter(type="T1558.001 - Golden ticket",user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)
    ticket_paths = []

    if len(golden_activities) > 0:
        for golden_activity in golden_activities:
            if golden_activity.results:
                if "ticket_path" in golden_activity.results:
                    exist = False
                    for ticket_path in ticket_paths:
                        if golden_activity.results["ticket_path"] in ticket_path:
                            exist = True
                            break
                    if exist == False:
                        ticket_paths.append((golden_activity.results["ticket_path"], golden_activity.results["ticket_path"]))

    print(ticket_paths)

    # recuperation des address ip :

    activities = Activity.objects.filter(user_id=request.user.id, type="Network scan",
                                         workspace_id=session["workspace"], results__isnull=False)
    list_ip_address = []

    if len(activities) > 0:
        for activity in activities:
            if activity.results is not None:
                activity_result = activity.results
                for key, value in activity_result.items():
                    exist = False
                    for ip_address in list_ip_address:
                        if key in ip_address:
                            exist = True
                            break
                    if exist == False:
                        list_ip_address.append((key, key))

    print(list_ip_address)

    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario
    if "scenario_name" in session:
        if len(ticket_paths) == 0:
            messages.error(request,
                           "the scenario was stopped because there is no tickets to execute pass the ticket")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})












    
    if request.method == 'POST':
        form = Ptt_form(request.POST)
        form.fields['ticket_path_choice'].choices = ticket_paths
        form.fields['ip_address_choice'].choices = list_ip_address
        

        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            ptt_name = form.cleaned_data['ptt_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="T1550.003 - Pass the ticket",
                                    name=ptt_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()



            ticket_path = ""
            ip_address = ""

            if form.cleaned_data["ticket_path"]:
                ticket_path = form.cleaned_data["ticket_path"]
                ip_address = form.cleaned_data["ip_address"]

            elif form.cleaned_data["ticket_path_choice"]:
                ticket_path = form.cleaned_data["ticket_path_choice"]
                ip_address = form.cleaned_data["ip_address_choice"]


            print("ticket path : " + ticket_path)
            print("ip_address : " + ip_address)


            # On lance la generation en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/pass-the-ticket.py", "--activity_id", str(max_id),
                 "--target_ip", ip_address, "--path_to_TGT", ticket_path,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-ptt')

    else:

        form = Ptt_form()
        form.fields['ticket_path_choice'].choices = ticket_paths
        form.fields['ip_address_choice'].choices = list_ip_address

        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_ptt.html', contexte)


#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_kerberoasting(request):

    session = request.session

    domain_controllers_dhn = []
    ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration", user_id=request.user.id,
                                                   workspace_id=session["workspace"], results__isnull=False)
    if len(ldap_enum_activities) > 0:
        for ldap_activity in ldap_enum_activities:
            if "domain_controllers" in ldap_activity.results:
                if len(ldap_activity.results["domain_controllers"]) > 0:
                    activity_domain_controllers = ldap_activity.results["domain_controllers"]
                    for domain_controller in activity_domain_controllers:
                        if domain_controller["dns_host_name"]:
                            exist = False
                            for dhn in domain_controllers_dhn:
                                if domain_controller["dns_host_name"] in dhn:
                                    exist = True
                                    break
                            if exist == False:
                                domain_controllers_dhn.append(
                                    (domain_controller["dns_host_name"], domain_controller["dns_host_name"]))

    print(domain_controllers_dhn)




    if request.method == 'POST':
        form = Kerberoasting_form(request.POST)
        form.fields['domain_controllers'].choices = domain_controllers_dhn

        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            kerberoasting_name = form.cleaned_data['kerberoasting_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"],
                                    type="T1558.003 - Kerberoasting",
                                    name=kerberoasting_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            domain_controler_ip = ""
            username = ""
            user_password = ""
            domain_name = ""

            if form.cleaned_data["domain_controler_ip"]:
                domain_controler_ip = form.cleaned_data["domain_controler_ip"]
                domain_name = form.cleaned_data["domain_name"]
                username = form.cleaned_data["username"]
                user_password = form.cleaned_data["user_password"]

            elif form.cleaned_data["domain_controllers"]:
                domain_controler_ip = form.cleaned_data["domain_controllers"]
                domain_name = form.cleaned_data["domain_name"]
                username = form.cleaned_data["username"]
                user_password = form.cleaned_data["user_password"]

            print("domain controler ip = " + str(domain_controler_ip))
            print("domain name = " + str(domain_name))
            print("username = " + str(username))
            print("user_password = " + str(user_password))

            # On lance la generation en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/Kerberoasting.py", "--activity_id", str(max_id),
                 "--ip_dc", domain_controler_ip, "--domain_name", domain_name, "--username", username, "--password", user_password,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-kerberoasting')

    else:

        form = Kerberoasting_form()
        form.fields['domain_controllers'].choices = domain_controllers_dhn

        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_kerberoasting.html', contexte)
    
    
    
    
#-----------------------------------------------------------------------------------------------------------------------

@login_required
def attacks_silver_ticket(request):

    session = request.session


    # Récupération des utilisateur a spoofer (admin + simple users)
    ldap_enum_activities = Activity.objects.filter(type="Ldap enumeration", user_id=request.user.id,
                                                   workspace_id=session["workspace"], results__isnull=False)
    domain_users = []
    if len(ldap_enum_activities) > 0:
        for ldap_activity in ldap_enum_activities:
            if "domain_users" in ldap_activity.results:
                if len(ldap_activity.results["domain_users"]) > 0:
                    activity_domain_users = ldap_activity.results["domain_users"]
                    for activity_domain_user in activity_domain_users:
                        if activity_domain_user["name"]:
                            exist = False
                            for domain_user_tuple in domain_users:
                                if activity_domain_user["name"] in domain_user_tuple:
                                    exist = True
                                    break
                            if exist == False:
                                domain_users.append((activity_domain_user["name"], activity_domain_user["name"]))

    print(domain_users)

    # récupérer les sid du domaine ( et peut etre de la machine cible local )

    list_choice_sid = []
    lsass_dump_activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") | Q(
        type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll"), user_id=request.user.id,
                                                    workspace_id=session["workspace"], results__isnull=False)

    if len(lsass_dump_activities) > 0:
        for lsass_dump_activity in lsass_dump_activities:
            if lsass_dump_activity.results["traitement"]:
                traitement = lsass_dump_activity.results["traitement"]
                for sid, dumps in traitement.items():
                    if dumps["domain_name"]:

                        treated_sid = sid.rsplit("-", 1)[0]
                        exist = False
                        for sid_tuple in list_choice_sid:
                            if treated_sid in sid_tuple:
                                exist = True
                                break
                        if exist == False:
                            list_choice_sid.append((treated_sid, dumps["domain_name"] + "-" + treated_sid))

    print(list_choice_sid)

    service_accounts = []
    password_cracking_activities = Activity.objects.filter(type="T1110.002 - Password cracking", user_id=request.user.id,workspace_id=session["workspace"], results__isnull=False)

    if len(password_cracking_activities) > 0:
        for password_cracking_activity in password_cracking_activities:
            if password_cracking_activity.results:
                password_cracking_results = password_cracking_activity.results
                if "kerberos_ticket" in password_cracking_results:
                    if password_cracking_results["kerberos_ticket"] == "yes":
                        if "service_ntlm_hash" in password_cracking_results:
                            my_spn_and_hash = password_cracking_results["username"].split("_")[0] + "-" + password_cracking_results["service_ntlm_hash"]
                            exist = False
                            for service_account in service_accounts:
                                if my_spn_and_hash in service_account:
                                    exist = True
                                    break
                            if exist == False:
                                service_accounts.append((my_spn_and_hash, "Service account : " + str(password_cracking_results["username"].split("_")[1])))


    print(service_accounts)



    # Cette partie c'est pour gérer les dependance dans la fonctionnalité scenario
    if "scenario_name" in session:
        if len(service_accounts) == 0 or len(list_choice_sid) == 0 or len(domain_users) == 0:
            messages.error(request, "the scenario was stopped because there is no information needed to forge a silver ticket")
            del session["scenario_name"]
            del session["scenario_steps"]
            del session["scenario_steps_length"]
            del session["current_scenario_step"]
            del session["current_scenario_step_status"]
            session.save()
            return render(request, 'attacks.html', {})







    if request.method == 'POST':
        form = Silver_ticket_form(request.POST)
        form.fields['domain_sid_choice'].choices = list_choice_sid
        form.fields['spoofed_username_choice'].choices = domain_users
        form.fields['spn_and_hash'].choices = service_accounts


        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            silver_ticket_name = form.cleaned_data['silver_ticket_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"],
                                    type="T1558.002 - Silver ticket",
                                    name=silver_ticket_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                session.save()

            service_ntlm_hash = ""
            domain_name = ""
            domain_sid = ""
            spoofed_username = ""
            spn = ""

            if form.cleaned_data["service_ntlm_hash"]:
                service_ntlm_hash = form.cleaned_data["service_ntlm_hash"]
                domain_name = form.cleaned_data["domain_name"]
                spoofed_username = form.cleaned_data["spoofed_username"]
                spn = form.cleaned_data["spn"]
                domain_sid = form.cleaned_data["domain_sid"]

            elif form.cleaned_data["spn_and_hash"]:
                service_ntlm_hash = form.cleaned_data["spn_and_hash"].split("-")[1]
                spn = form.cleaned_data["spn_and_hash"].split("-")[0]
                domain_name = form.cleaned_data["domain_name"]
                spoofed_username = form.cleaned_data["spoofed_username_choice"]
                domain_sid = form.cleaned_data["domain_sid_choice"]



            print("service ntlm hash = " + str(service_ntlm_hash))
            print("domain name = " + str(domain_name))
            print("spoofed username = " + str(spoofed_username))
            print("spn = " + str(spn))
            print("domain sid = " + str(domain_sid))

            # On lance la generation en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/silver-ticket-attack.py", "--activity_id", str(max_id),
                 "--nthash_service", service_ntlm_hash, "--domain_name", domain_name, "--username", spoofed_username, "--domain_sid", domain_sid, "--spn", spn,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-silver_ticket')

    else:

        form = Silver_ticket_form()
        form.fields['domain_sid_choice'].choices = list_choice_sid
        form.fields['spoofed_username_choice'].choices = domain_users
        form.fields['spn_and_hash'].choices = service_accounts


        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_silver_ticket.html', contexte)













    

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def attacks_port_listener(request):

    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    # On recupere les paylods possible pour le multi/handler:

    client = MsfRpcClient('anis', ssl=True)
    exploit = client.modules.use('exploit', 'multi/handler')
    payloads = exploit.payloads
    banned_chars = ["/vncinject/", "powershell", "/custom", "/peinject/", "/upexec/", "pingback", "/exec",
                    "/messagebox"]
    allowed_chars = ["/shell", "/meterpreter"]
    filtred_payloads = []
    for payload in payloads:
        test = False
        test2 = False
        for allowed_char in allowed_chars:
            if payload.find(allowed_char) != -1:
                for banned_char in banned_chars:
                    if payload.find(banned_char) != -1:
                        test = True
                        break
                test2 = True
                break

        if test == False and test2 == True:
            filtred_payloads.append((payload, payload))

    filtred_payloads = tuple(filtred_payloads)

    session = request.session
    if request.method == 'POST':
        form = Port_listener_form(request.POST, choices=filtred_payloads)
        # check if form is valid :
        if form.is_valid():
            # enregistrer au niveau de la BDD
            port_listener_name = form.cleaned_data['port_listener_name']
            Activity.objects.create(user_id=request.user.id, workspace_id=session["workspace"], type="Port listener",
                                    name=port_listener_name,
                                    begin_date=datetime.now())

            # Recuperer le plus grand id de la table Activity :
            max_id = Activity.objects.aggregate(Max('id'))['id__max']

            # Dans le cas ou un scenario est en cours :
            session = request.session
            if "scenario_name" in session:
                session["current_scenario_step_status"] = "running"
                session["current_step_id"] = max_id
                current_scenario_step = session["current_scenario_step"]
                session["scenario_steps"][current_scenario_step]["activity_id"] = max_id
                session.save()

            port_listener_payload = form.cleaned_data["payload"]
            port_listener_port = form.cleaned_data["port"]
            # On lance l'enumeration en arrière plan :

            subprocess.Popen(
                ["python", "My_app/scripts/port_listenner.py", "--activity_id", str(max_id),
                 "--port", port_listener_port, "--payload", port_listener_payload,
                 ])

            return redirect('My_app-activite')
        else:
            return redirect('attacks-port_listener')

    else:

        form = Port_listener_form(choices=filtred_payloads)
        contexte = {
            'form': form,
        }
        return render(request, 'attacks/attacks_port_listener.html', contexte)

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_scenario(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    session = request.session
    if request.method == "POST":
        if "tactic_choice" in request.POST:
            tactic = request.POST.get("tactic_choice")
            technique = request.POST.get("technique_choice")
            procedure = request.POST.get("procedure_choice")
            step_info = {
                'tactic': tactic,
                'technique': technique,
                'procedure': procedure,
            }

            scenario_id = request.POST.get("scenario_id")
            print(scenario_id)

            #recuperer l'enregistrement associé:
            scenario = Scenario.objects.get(id=scenario_id)
            #recuperer les etape du scenario:
            scenario_steps = scenario.scenario_steps
            if scenario_steps == None:
                scenario_steps = []
            # Dans le cas ou on veut ajouter une technique de post exploitation on doit verifier d'abord si il existe
            # une technique d'initial access
            if tactic != "reconnaissance" and tactic != "initial_access" and tactic != "local" and tactic != "lateral_mouvement":
                test = False
                for step in scenario_steps:
                    if step["tactic"] == "initial_access":
                        test = True
                        break

                if test == True:
                    # ajouter au scenario l'etape choisie
                    scenario_steps.append(step_info)
                    # Mettre a jour l'enregistrement du scenario:
                    scenario.scenario_steps = scenario_steps
                    scenario.save()
                else:
                    messages.error(request, "you must first add an initial access technique")

            # dans le cas ou on veut rajouter une technique d'initial access, il ne faudrait pas qu'il existe deja
            # une technique d'intial access dans le scenario. si tu veux supprimer cette restriction, commente
            # ce elif

            #elif tactic == "initial_access":
                #test = False
                #for step in scenario_steps:
                    #if step["tactic"] == "initial_access":
                        #test = True
                        #break
                #if test == True:
                    #messages.error(request, "you have already added an initial_access technique")
                #else:
                    # ajouter au scenario l'etape choisie
                    #scenario_steps.append(step_info)
                    # Mettre a jour l'enregistrement du scenario:
                    #scenario.scenario_steps = scenario_steps
                    #scenario.save()
            else:
                # ajouter au scenario l'etape choisie
                scenario_steps.append(step_info)
                # Mettre a jour l'enregistrement du scenario:
                scenario.scenario_steps = scenario_steps
                scenario.save()

            url = reverse("My_app-scenario")
            url = url + "?modify_id=" + str(scenario_id)
            return redirect(url)

        else:
            form = My_app_addscenario(request.POST)
            if form.is_valid():
                scenario_name = form.cleaned_data["scenario_name"]
                Scenario.objects.create(user_id=request.user.id, scenario_name=scenario_name, workspace_id=session["workspace"])

            form = My_app_addscenario()
            queryset = Scenario.objects.filter(user_id=request.user.id, workspace_id=session["workspace"])
            print(queryset)

            contexte = {
                "scenario_list": queryset,
                "form": form,
            }
            return render(request, 'scenario.html', contexte)
    else:
        if "use_id" in request.GET:
            scenario_id = request.GET.get("use_id")
            session = request.session
            scenario = Scenario.objects.get(id=scenario_id)

            scenario_steps = scenario.scenario_steps
            if scenario_steps == None:
                messages.error(request, "the scenario does not contain any activity")
                return redirect("My_app-scenario")
            else:
                session["scenario_name"] = scenario.scenario_name
                session["scenario_steps"] = scenario.scenario_steps
                session["scenario_steps_length"] = len(scenario.scenario_steps)
                session["current_scenario_step"] = 0
                session["current_scenario_step_status"] = "sleeping"

                return redirect("My_app-attacks")






        elif "modify_id" in request.GET:
            # recuperer l'id du scenario
            scenario_id = request.GET.get("modify_id")
            # recuperer l'enregistrement associé:
            scenario = Scenario.objects.get(id=scenario_id)
            #recuperer les etapes du scenario:
            scenario_steps = scenario.scenario_steps
            if scenario_steps == None:
                scenario_steps = [] # pour dire qu'il ne contient pas d'etapes
            #instancier le formulaire
            form = Scenario_add_activity()

            contexte = {
                'form': form,
                'scenario_steps': scenario_steps,
                'scenario_id': scenario_id,
            }
            return render(request, 'scenario/scenario_add_activity.html', contexte)

        elif "stop_scenario" in request.GET:
            if "scenario_name" in session:

                messages.error(request,
                               "the scenario was stopped")
                del session["scenario_name"]
                del session["scenario_steps"]
                del session["scenario_steps_length"]
                del session["current_scenario_step"]
                del session["current_scenario_step_status"]
                session.save()

            return redirect('My_app-scenario')





        else:
            form = My_app_addscenario()
            queryset = Scenario.objects.filter(user_id=request.user.id, workspace_id=session["workspace"])
            print(queryset)

            contexte = {
                "scenario_list": queryset,
                "form": form,
            }
            return render(request, 'scenario.html', contexte)

#-----------------------------------------------------------------------------------------------------------------------
# cette vue est utilisée pour recuperer les technique de la tactic approprié dans le formulaire de la page scenario_add_activity.html
def maj_technique_choice(request):
    tactic = request.GET.get('tactic', None)

    technique_choice = [("---", "---")]
    if tactic == "reconnaissance":
        technique_choice.append(("scan_ip_blocks", "T1595.001 - Scanning ip blocks"))
        technique_choice.append(("vuln_scan", "T1595.002 - Vulnerability scanning"))
        #technique_choice.append(("account_discovery", "T1087 - account discovery"))
    elif tactic == "initial_access":
        technique_choice.append(("exploitation", "Exploitation"))
    elif tactic == "lateral_mouvement":
        technique_choice.append(("pass_the_hash", "T1550.002 - Pass the hash"))
        technique_choice.append(("pass_the_ticket", "T1550.003 - Pass the ticket"))
    elif tactic == "local":
        technique_choice.append(("account_discovery", "T1087 - account discovery"))
        technique_choice.append(("T1110.002_password_cracking", "T1110.002 - Password cracking"))
        technique_choice.append(("T1003.006_dcsync", "T1003.006 - DCSync"))
        technique_choice.append(("T1558.001_golden_ticket", "T1558.001 - Forge golden tickets"))
        technique_choice.append(("T1558.003_kerberoasting", "T1558.003 - Kerberoasting"))
        technique_choice.append(("T1558.002_silver_ticket", "T1558.002 - Silver ticket"))
    elif tactic == "others":
        technique_choice.append(("...", "..."))
    else:
        origin_dir_path = os.path.abspath(os.getcwd())

        tactic_directory = os.path.join("My_app/scripts/atomics", tactic)
        os.chdir(tactic_directory)

        dir_path = os.path.abspath(os.getcwd())

        #Ajouter d'abord les technique faites localement par nous meme
        if tactic == "credential_access":
            technique_choice.append(("T1110.002_password_cracking", "T1110.002 - Password cracking"))
            technique_choice.append(("T1003.006_dcsync", "T1003.006 - DCSync"))
            technique_choice.append(("T1558.001_golden_ticket", "T1558.001 - Forge golden tickets"))
            technique_choice.append(("T1558.003_kerberoasting", "T1558.003 - Kerberoasting"))
            technique_choice.append(("T1558.002_silver_ticket", "T1558.002 - Silver ticket"))

        if tactic == "discovery":
            technique_choice.append(("account_discovery", "T1087 - account discovery"))
        #Ajouter les autres technique qui s'executent sur la machine cible
        for element in os.listdir(dir_path):
            # Vérifie si l'élément est un répertoire
            if os.path.isdir(os.path.join(dir_path, element)):
                os.chdir(element)
                # Récuperer tout les fichiers qui se terminent par .yaml
                yaml_files = glob.glob("*yaml")

                # Ouvre le fichier YAML en mode lecture
                with open(yaml_files[0], 'r') as file:
                    # Charge le contenu du fichier YAML
                    yaml_data = yaml.safe_load(file)

                attack_technique = yaml_data['attack_technique']
                display_name = yaml_data['display_name']
                technique_info = attack_technique + " - " + display_name

                technique_choice.append((attack_technique, technique_info))
                os.chdir(dir_path)

        os.chdir(origin_dir_path)


    return JsonResponse(technique_choice, safe=False)


#-----------------------------------------------------------------------------------------------------------------------
# cette vue est utilisée pour recuperer les procedure de la technique approprié dans le formulaire de la page scenario_add_activity.html
def maj_procedure_choice(request):
    tactic = request.GET.get("tactic")
    technique = request.GET.get("technique")

    procedure_choice = []
    print(technique)
    if technique == "scan_ip_blocks":
        procedure_choice.append(("network_scan", "Network scan"))
    elif technique == "vuln_scan":
        procedure_choice.append(("vuln_scan", "Vulnerability scanning"))
    elif technique == "account_discovery":
        procedure_choice.append(("ldap_enum", "Ldap enumeration"))
        procedure_choice.append(("smb_enum", "SMB enumeration"))
    elif technique == "exploitation":
        procedure_choice.append(("exploitation", "Exploitation"))
    elif technique == "pass_the_hash":
        procedure_choice.append(("pth_crackmapexec", "Pass the hash using crackmapexec"))
    elif technique == "T1110.002_password_cracking":
        procedure_choice.append(("password_cracking_john","crack passwords offline with john the ripper"))
    elif technique == "T1003.006_dcsync":
        procedure_choice.append(("dcsync_secretdump", "DCSync using secretdump"))
    elif technique == "T1558.001_golden_ticket":
        procedure_choice.append(("golden_ticket_ticketer", "Forge golden tickets using ticketer"))
    elif technique == "pass_the_ticket":
        procedure_choice.append(("ptt_crackmapexec", "Pass the ticket using crackmapexec"))
    elif technique == "T1558.003_kerberoasting":
        procedure_choice.append(("kerberoasting_impacket", "Kerberoasting using impacket scripts"))
    elif technique == "T1558.002_silver_ticket":
        procedure_choice.append(("silver_ticket_impacket", "Forge silver tickets using ticketer from impacket"))
    elif technique == "...":
        procedure_choice.append(("port_listener", "Port listener"))
    else:

        origin_dir_path = os.path.abspath(os.getcwd())

        technique_directory = os.path.join("My_app/scripts/atomics", tactic, technique)
        os.chdir(technique_directory)

        dir_path = os.path.abspath(os.getcwd())

        yaml_files = glob.glob("*yaml")

        # Ouvre le fichier YAML en mode lecture
        with open(yaml_files[0], 'r') as file:
            # Charge le contenu du fichier YAML
            yaml_data = yaml.safe_load(file)

        atomic_tests = yaml_data["atomic_tests"]

        for atomic_test in atomic_tests:
            procedure_choice.append((atomic_test["name"], atomic_test["name"]))

        os.chdir(origin_dir_path)

    return JsonResponse(procedure_choice, safe=False)



#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_user(request):
    contexte = {

    }
    return render(request, 'user.html', contexte)

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_logout(request):
    logout(request)
    return redirect("authenticate-index")

#-----------------------------------------------------------------------------------------------------------------------
@login_required
def My_app_rapport(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    if request.method == 'POST' and 'download' in request.POST:
        # Téléchargement du rapport depuis la session
        encoded_content = request.session.get('report_buffer')
        if encoded_content:
            # Décodage du contenu en base64
            report_content = base64.b64decode(encoded_content)

            # Définir les en-têtes de réponse pour le téléchargement
            response = HttpResponse(report_content, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="rapport.pdf"'

            # Écrire le contenu du rapport dans la réponse
            #response.write(report_content)
            return response
    elif request.method == "GET":

        #  créer un objet de flux d'octets en mémoire.
        buffer = BytesIO()
        # Instancier le fichier pdf
        filename = "rapport.pdf"
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        story = []

        # -------- Ajouter du contenue au fichier pdf ---------
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        paragraph_style = styles["BodyText"]

        # 0 ---> creation des styles personnalisés

        # Style personnalisé pour les sous-titres avec numérotation
        numbered_subtitle_style = ParagraphStyle(
            "NumberedSubtitle",
            parent=styles["Heading2"],
            alignment=enums.TA_LEFT,
            leftIndent=20,
            spaceBefore=10,
            spaceAfter=10,
            bulletFontSize=8,
            bulletAnchor="start",
            bulletFormat="(1)",
        )

        # Style du tableau
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),  # Couleur de fond des titres de colonnes
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),  # Couleur du texte des titres de colonnes
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Police du texte des titres de colonnes
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),  # Alignement du texte des titres de colonnes
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  # Marge inférieure des titres de colonnes
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),  # Couleur de fond des lignes de données
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),  # Couleur du texte des lignes de données
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),  # Police du texte des lignes de données
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),  # Alignement du texte des lignes de données
            ('GRID', (0, 0), (-1, -1), 1, colors.black),  # Lignes de la grille du tableau
            ('WORDWRAP', (0, 0), (-1, -1)),  # Enable word wrap for all cells
        ])

        # instancier les numérotation des titres et sous-titres etc..
        subtitle_number = 1
        sub_subtitle_number = [1,1]

        #  -- > Ajouter le titre ------
        # recuperer le titre du workspace
        workspace = Workspaces.objects.get(id=request.session["workspace"])

        # creation du titre
        title = "Project Report: " +str(workspace.name)
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2 * inch))

        # -- > Ajout d'une description -------
        description = "This report is provided to present the results and recommendations following a thorough assessment of the security of a system or application. Its purpose is to inform stakeholders about identified vulnerabilities and associated potential risks. The aim of this report is to support system owners and administrators in making informed decisions to enhance the security of their infrastructure. By providing a detailed analysis of identified weaknesses, this report enables the appropriate measures to be taken to mitigate risks and protect critical assets of the organization"
        story.append(Paragraph(description, paragraph_style))
        story.append(Spacer(1, 0.1 * inch))

        # recupérer toutes les activités de scan réseau de l'utilisateur
        session = request.session
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="Network scan", results__isnull=False)

        # on vérifie d'abord est ce qu'il y'a une activité de scan réseau qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:

            #  -- > Sous-titre : Scan de bloc d'adresse IP ------
            subtitle = str(subtitle_number) + ". Scanning ip blocks"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            #  -- Description de la technique : scan de block d'adresse IP
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Adversaries can analyze IP blocks to gather information about the victims' network, such as actively used IP addresses and more detailed information about the hosts to which these addresses have been assigned."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            #  -- > Résultats des activités de la technique : scan de block d'adresse IP
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1




            # On affiche le résultat de chaque activité individuellement
            for activity in activities:
                if activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    #premier tableau
                    table_data = [
                        # Titres des colonnes
                        ['Machine', 'Status', 'hostname'],
                        ]

                    for key, val in activity.results.items():
                        table_data.append([key, val["state"], val["hostname"]])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)
                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

                    # Deuxième tableau
                    table_data = [
                        # Titres des colonnes
                        ['Machine', 'OS_match name', 'OS_match accuracy', 'OS_match line'],
                    ]
                    #Paragraph("<pre>" + key2.replace(',', "\n") + "</pre>", styles['Normal'])
                    for key, val in activity.results.items():
                        for key2, val2 in val["os"].items():
                            table_data.append([key, Paragraph(key2, paragraph_style), val2["osmatch_accuracy"], val2["osmatch_line"]])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)
                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

                    #Troisième tableau
                    table_data = [
                        # Titres des colonnes
                        ['Machine', 'Port', 'Protocol', 'Status', 'Service', 'Version'],
                    ]

                    for key, val in activity.results.items():
                        for key2, val2 in val["port"].items():
                            table_data.append([key, key2, val2["protocol"], val2["status"], Paragraph(val2["service"], paragraph_style), Paragraph(val2["version"], paragraph_style)])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)


                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            #  -- > recommendation de la technique : scan de block d'adresse IP
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - This technique cannot be easily mitigated by preventative controls as it relies on behaviors performed outside the scope of enterprise defenses and controls. Efforts should focus on minimizing the amount and sensitivity of data available to external parties"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Monitor network data for unusual data flows. Processes that utilize the network but typically do not have network communication or have never been observed before are considered suspicious."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

        # -- > Sous-titre : scan de vulnérabilités

        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="vuln scan", results__isnull=False)

        # on vérifie d'abord est ce qu'il y'a une activité de scan de vuln qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:

            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". Vulnerability scanning"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : scan de vulnérbilités
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Adversaries can analyze victims for vulnerabilities that can be exploited during targeting. Vulnerability scans typically check if the configuration of a target host/application (e.g., software and version) potentially aligns with a specific exploit target that the adversary may seek to utilize"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            # -- > Résultats de la technique : scan de vulnérabilités


            for activity in activities:
                if activity.results and "result" in activity.results["get_reports_response"]["report"]["report"]["results"]:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))
                    vulns = {}
                    if activity.results is not None:
                        for vuln in activity.results["get_reports_response"]["report"]["report"]["results"]["result"]:
                            vulns[vuln['@id']] = {
                                "name": vuln["name"],
                                "host": vuln["host"]["#text"],
                                "port": vuln["port"],
                                "severity": vuln["severity"],
                            }
                            list_ref = []
                            if vuln['nvt'].get('refs') is not None:
                                if isinstance(vuln['nvt']["refs"]["ref"], dict) and vuln['nvt']['refs']['ref'].get(
                                        "@type") is not None:
                                    vuln_ref = {
                                        "type": vuln['nvt']['refs']['ref']["@type"],
                                        "id": vuln['nvt']['refs']['ref']["@id"],
                                    }
                                    list_ref.append(vuln_ref)
                                else:
                                    for reference in vuln["nvt"]["refs"]["ref"]:
                                        if reference.get("@type") is not None:
                                            vuln_ref = {
                                                "type": reference["@type"],
                                                "id": reference["@id"],

                                            }

                                            list_ref.append(vuln_ref)
                            if len(list_ref) != 0:
                                vulns[vuln["@id"]]["refs"] = list_ref

                        # premier tableau
                        table_data = [
                            # Titres des colonnes
                            ['Name', 'Machine', 'Port', 'Severity'],
                        ]

                        refs = []
                        for key, value in vulns.items():
                            refs = []
                            if "refs" in value:
                                for ref in value["refs"]:
                                    refs.append(ref["id"])

                            if len(refs) > 0:
                                refs = '\n'.join(refs)
                            else:
                                refs = ''

                            table_data.append([Paragraph(value['name'], paragraph_style), Paragraph(value['host'], paragraph_style), Paragraph(value['port'], paragraph_style), Paragraph(value['severity'], paragraph_style)])



                        # Calculer la largeur de chaque colonne
                        num_columns = len(table_data[0])
                        column_width = 500 / num_columns
                        # Création du tableau
                        table = Table(table_data, colWidths=[column_width])
                        table.setStyle(table_style)
                        story.append(table)
                        story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations de la technique : scan de vulnérbilités
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Due to relying on behaviors outside the scope of enterprise defenses and controls, this technique cannot be easily mitigated by preventative measures. Efforts should instead focus on minimizing the quantity and sensitivity of data accessible to external parties"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Monitor network data for abnormal data flows. Processes that utilize the network but typically do not engage in network communication or have not been observed before are considered suspicious"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))


        # -- > sous-titre pour la technique : énumeration ldap
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="Ldap enumeration", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de LDAP enumeration qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:

            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". LDAP Enumeration"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : Enumeration LDAP
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "The adversaries employ LDAP queries to enumerate various elements, such as user information, groups, computers, and much more."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : Enumeration LDAP
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1



            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    # premier tableau
                    table_data = [
                        # Titres des colonnes
                        ['Name', 'OS', 'dns hostname'],
                    ]


                    for domain_controller in activity.results["domain_controllers"]:
                        table_data.append([Paragraph(domain_controller["name"], paragraph_style), Paragraph(domain_controller['operating_system'], paragraph_style), Paragraph(domain_controller["dns_host_name"], paragraph_style)])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

                    # deuxième tableau

                    table_data = [
                        # Titres des colonnes
                        ['Name', 'Distinguished name', 'mail'],
                    ]

                    for domain_admin in activity.results["domain_admins"]:
                        for key, val in domain_admin.items():
                            if val == None:
                                domain_admin[key] = ""
                        table_data.append([Paragraph(domain_admin["name"], paragraph_style), Paragraph(domain_admin["distinguishedName"], paragraph_style), Paragraph(domain_admin["mail"], paragraph_style)])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

                    #Troisième tableau

                    table_data = [
                        # Titres des colonnes
                        [Paragraph('Nom', paragraph_style), Paragraph('User principal name (UPN)', paragraph_style), Paragraph('mail', paragraph_style), Paragraph('description', paragraph_style), Paragraph('Member of', paragraph_style)],
                    ]

                    for domain_user in activity.results["domain_users"]:
                        for key, val in domain_user.items():
                            if val == None:
                                domain_user[key] = ""
                            if isinstance(val, list):
                                val = "\n".join(val)
                                domain_user[key] = val

                        table_data.append([Paragraph(domain_user["name"], paragraph_style),
                                           Paragraph(domain_user["user_principal_name"], paragraph_style),
                                           Paragraph(domain_user["mail"], paragraph_style),
                                           Paragraph(domain_user["description"], paragraph_style),
                                           Paragraph(domain_user["membre_de"], paragraph_style),])


                    # Création du tableau
                    table = Table(table_data, colWidths=[60, 70, 70, 100, 200])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))




        # -- > sous-titre : smb-enumeration:
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="SMB enumeration", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de LDAP enumeration qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:

            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". SMB Enumeration"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : Enumeration SMB
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "SMB enumeration is a multi-stage process in which we gather various information from the target host or system, including host names, shared listing, null sessions, vulnerability scanning, and more."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : Enumeration SMB
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            title_style = ParagraphStyle(
                name='TableColumnTitle',)

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    table_data = [
                        # Titres des colonnes
                        ['@ip', '@mac', 'FQDN', 'WG', 'OS',],
                    ]

                    table2_data = [
                        ['computer name', Paragraph('SMB auth level', title_style), Paragraph('SMB_challenge_response', title_style), 'smb signature', 'smbv2 signature'],
                    ]

                    for host, info in activity.results.items():
                        table_data.append([
                            Paragraph(info["host_ip"], paragraph_style),
                            Paragraph(info["mac_addr"], paragraph_style),
                            Paragraph(info["FQDN"], paragraph_style),
                            Paragraph(info["workgroup"], paragraph_style),
                            Paragraph(info["OS"], paragraph_style),
                        ])
                        table2_data.append([
                            Paragraph(info["computer_name"], paragraph_style),
                            Paragraph(info["smb_authentication_level"], paragraph_style),
                            Paragraph(info["smb_challenge_response"], paragraph_style),
                            Paragraph(info["smb_signature"], paragraph_style),
                            Paragraph(info["smb_v2_signature"], paragraph_style)
                        ])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)
                    table2 = Table(table2_data, colWidths=[column_width])
                    table2.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))
                    story.append(table2)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : SMB Enumeration
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Divide your network into segments to limit the accessibility of SMB services, reducing the attack surface for potential enumeration. <br /> - Implement strong access controls and permissions to restrict unauthorized users from accessing sensitive SMB resources."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Use network monitoring tools to capture and analyze SMB traffic. <br /> - Monitor event logs on SMB servers and domain controllers for relevant events related to authentication, access, or failed login attempts."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

        # kerberoasting ---------------
        # -- > Sous-titre pour la technique : kerberoasting
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1558.003 - Kerberoasting", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de kerberoasting qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1558.003 - Kerberoasting"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : kerberoasting
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Kerberoasting is an exploitation technique that takes advantage of the Kerberos protocol to gather password hashes for user accounts in Active Directory, specifically those associated with servicePrincipalName (SPN) values, commonly known as service accounts.By leveraging the protocol, a user can acquire a ticket-granting service (TGS) ticket for any given SPN. Certain sections of the TGS ticket may be encoded with RC4 encryption, utilizing the password hash of the corresponding service account as the encryption key. Consequently, if an adversary manages to acquire TGS tickets, either by extracting them from memory or by intercepting network traffic, they can extract the password hash of the service account and launch an offline brute force attack to uncover the actual plaintext password."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : kerberoasting
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    paragraph = "here are the service accounts found : "
                    story.append(Paragraph(paragraph, paragraph_style))
                    story.append(Spacer(1, 0.1 * inch))

                    table_data = [
                        # Titres des colonnes
                        ['Service', 'SPN', 'Acount'],
                    ]

                    if "services" in activity.results:
                        services = activity.results["services"]
                        for service in services:

                            table_data.append([Paragraph(str(service["service"]), paragraph_style), Paragraph(str(service["SPN"]), paragraph_style), Paragraph(str(service["computer_service"]), paragraph_style)])


                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : kerberoasting
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Enable AES Kerberos encryption (or another stronger encryption algorithm), rather than RC4, where possible. <br /> - Limit service accounts to minimal required privileges, including membership in privileged groups such as Domain Administrators."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Monitor for anomalous Kerberos activity, such as enabling Audit Kerberos Service Ticket Operations to log Kerberos TGS service ticket requests."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))








        # -- > Sous-titre pour la technique : Exploitation
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="Exploitation", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de LDAP enumeration qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". Vulnerability exploitation"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : Exploitation
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Vulnerability exploitation involves the deliberate act of identifying and taking advantage of security weaknesses or vulnerabilities in systems, software, or networks. Attackers exploit these vulnerabilities to gain unauthorized access, compromise data, execute malicious code, or carry out other nefarious activities."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : Exploitation
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    # On doit vérifier si l'exploitation a marché ou bien non ( l'affichage dépendra de ca )
                    if "session_uuid" in activity.results: # Dans ce cas l'exploitation a marché
                        paragraphe = "Vulnerability name : " + activity.results["vuln_name"] + "<br />" + "Targeted machine : " + activity.results["target_ip"] + " (OS = " + activity.results["session_os"] + ") <br />" + "Selected exploit : " + activity.results["exploit"] + "<br />" + "Selected payload : " + activity.results["payload"] + "<br />" + "Status: The vulnerability exploitation was successful."

                    else:
                        paragraphe = "Vulnerability name : " + activity.results["vuln_name"] + "<br />" + "Targeted machine : " + activity.results["target_ip"] + "Selected exploit : " + activity.results["exploit"] + "<br />" + "Selected payload : " + activity.results["payload"] + "<br />" + "Status: The vulnerability exploitation activity did not succeed."

                    paragraphe = Paragraph(paragraphe, paragraph_style)
                    story.append(paragraphe)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : exploitation
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            paragraphe = " - Regularly update systems and software with the latest security patches to address known vulnerabilities. <br /> - Conduct periodic vulnerability scans to identify and remediate weaknesses before they can be exploited. <br /> - Enforce the principle of least privilege, granting users only the access rights necessary for their roles."
            story.append(Paragraph(paragraphe, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            paragraphe = " - Deploy IDS/IPS solutions that can detect and alert on suspicious network activity indicative of exploit attempts or unauthorized access. <br /> - Monitor system logs, including event logs and access logs, for abnormal or suspicious activities. "
            story.append(Paragraph(paragraphe, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

        # -- > sous-titre pour la technique : password cracking
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1110.002 - Password cracking", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de LDAP enumeration qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". Password cracking"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : password cracking
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Hackers can employ password cracking to attempt to retrieve usable credentials, such as plaintext passwords, when elements of identification like password hashes are obtained"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : password cracking
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    if "kerberos_ticket" in activity.results:
                        if activity.results["kerberos_ticket"] == "yes":
                            paragraph = "Encrypted tgs ticket cracking activity <br /> Hash type : " + activity.results["hash_type"]
                            story.append(Paragraph(paragraph, paragraph_style))
                            story.append(Spacer(1, 0.1 * inch))
                        else:

                            paragraph = "Hash : " + activity.results["hash_value"] + "<br /> Hash type : " + activity.results["hash_type"]
                            story.append(Paragraph(paragraph, paragraph_style))
                            story.append(Spacer(1, 0.1 * inch))
                    else:
                        paragraph = "Hash : " + activity.results["hash_value"] + "<br /> Hash type : " + \
                                    activity.results["hash_type"]
                        story.append(Paragraph(paragraph, paragraph_style))
                        story.append(Spacer(1, 0.1 * inch))


                    table_data = [
                        # Titres des colonnes
                        ['Cracked', 'Username', 'Password'],
                    ]

                    if "crack_stat" in activity.results and "username" in activity.results and "password" in activity.results:

                        table_data.append([Paragraph(str(activity.results["crack_stat"]), paragraph_style), Paragraph(str(activity.results["username"]), paragraph_style), Paragraph(str(activity.results["password"]), paragraph_style)])


                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : password cracking
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- Utilize multi-factor authentication. Whenever possible, enable multi-factor authentication for external services as well. <br /> - Refer to NIST guidelines when creating password policies. "
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))


        # -- > sous titre : T1003.002-Dump-SAM-With-Mimikatz
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1003.002-Dump-SAM-With-Mimikatz", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de dump sam qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                if "traitement" in activity.results:
                    verif = True
                    break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1003.002-Dump-SAM-With-Mimikatz"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : T1003.002-Dump-SAM-With-Mimikatz
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "The SAM database, which stores credential material, can be targeted by adversaries who employ in-memory techniques or exploit the Windows Registry in their attempts to extract this information."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : dump sam
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    if "traitement" in activity.results:
                        if activity.results["traitement"]:
                            # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                            subtitle = activity.name
                            subtitle_style = styles["Heading4"]
                            story.append(Paragraph(subtitle, subtitle_style))



                            table_data = [
                                # Titres des colonnes
                                ['RID', 'Username', 'NTLM Hash'],
                            ]

                            traitement = activity.results["traitement"]
                            for key, val in traitement.items():

                                table_data.append([Paragraph(str(key), paragraph_style), Paragraph(str(val["User"]), paragraph_style), Paragraph(val["Hash_NTLM"], paragraph_style)])


                            # Calculer la largeur de chaque colonne
                            num_columns = len(table_data[0])
                            column_width = 500 / num_columns
                            # Création du tableau
                            table = Table(table_data, colWidths=[column_width])
                            table.setStyle(table_style)

                            story.append(table)
                            story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : dump sam
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Ensure that local administrator accounts have complex, unique passwords across all systems on the network <br/> - It is advisable to avoid adding user or admin domain accounts to the local administrator groups on various systems, unless they are under strict control."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Keep a vigilant eye on executed commands and their corresponding arguments that have the potential to extract credential material from the Security Account Manager (SAM) database. Such attempts can occur through in-memory techniques or by accessing the Windows Registry, where the SAM database is located. <br /> - Monitor for the SAM registry key dump being created to access stored account password hashes. "
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))



        # -- > sous titre : T1003.005-Cached Credential Dump via Mimikatz

        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1003.005-Cached Credential Dump via Mimikatz", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de dump sam qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                if "traitement" in activity.results:
                    verif = True
                    break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1003.005-Cached Credential Dump via Mimikatz"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : T1003.005-Cached Credential Dump via Mimikatz
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "In an attempt to ensure authentication continuity when a domain controller is unavailable, adversaries may try to gain access to cached domain credentials."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : cached dump
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    if "traitement" in activity.results:
                        if activity.results["traitement"]:
                            # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                            subtitle = activity.name
                            subtitle_style = styles["Heading4"]
                            story.append(Paragraph(subtitle, subtitle_style))



                            table_data = [
                                # Titres des colonnes
                                ['RID', 'Username', 'MsCacheV2'],
                            ]

                            traitement = activity.results["traitement"]
                            for key, val in traitement.items():

                                table_data.append([Paragraph(str(key), paragraph_style), Paragraph(str(val["User"]), paragraph_style), Paragraph(str(val["MsCacheV2"]), paragraph_style)])


                            # Calculer la largeur de chaque colonne
                            num_columns = len(table_data[0])
                            column_width = 500 / num_columns
                            # Création du tableau
                            table = Table(table_data, colWidths=[column_width])
                            table.setStyle(table_style)

                            story.append(table)
                            story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : cached dump
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - It is advisable to include users in the Active Directory security group named Protected Users. This measure aids in restricting the caching of users' plaintext credentials. <br /> - Give careful consideration to the act of restricting the number of cached credentials (HKLM\SOFTWARE\Microsoft\Windows NT\Current Version\Winlogon\cachedlogonscountvalue)."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Closely monitor executed commands and their associated arguments that might try to access cached domain credentials used for authentication in situations where a domain controller is not accessible."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))


        # -- > sous-titre : Dump LSASS

        activities = Activity.objects.filter(Q(type="T1003.001-Dump LSASS.exe Memory using comsvcs.dll") | Q(type="T1003.001-Dump LSASS.exe Memory using ProcDump") ,user_id=request.user.id, workspace_id=session["workspace"],
                                             results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de dump lsass qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                if "traitement" in activity.results:
                    verif = True
                    break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1003.001-Dump LSASS.exe Memory"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : T1003.001 dump lsass
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Adversaries might try to gain access to credential material stored within the process memory of the Local Security Authority Subsystem Service (LSASS). Once a user logs on, various types of credential materials are generated and stored in the LSASS process memory. These materials can be extracted by an administrative user or the SYSTEM account, and then utilized for Lateral Movement by leveraging Use Alternate Authentication Material."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : dump lsass
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    if "traitement" in activity.results:
                        if activity.results["traitement"]:
                            # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                            subtitle = activity.name
                            subtitle_style = styles["Heading4"]
                            story.append(Paragraph(subtitle, subtitle_style))



                            table_data = [
                                # Titres des colonnes
                                [Paragraph('username', paragraph_style), Paragraph('lm hash', paragraph_style), Paragraph('ntlm hash', paragraph_style), Paragraph('password', paragraph_style)],
                            ]


                            traitement = activity.results["traitement"]

                            for key, val in traitement.items():

                                table_data.append([Paragraph(str(val["username"]), paragraph_style), Paragraph(str(val["lm_hash"]), paragraph_style), Paragraph(str(val["ntlm_hash"]), paragraph_style), Paragraph(str(val["password"]), paragraph_style)])


                            # Calculer la largeur de chaque colonne
                            num_columns = len(table_data[0])
                            column_width = 500 / num_columns
                            # Création du tableau
                            table = Table(table_data, colWidths=[column_width])
                            table.setStyle(table_style)

                            story.append(table)
                            story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : at
            subtitle = str(sub_subtitle_number[0]) + "." + str(
                sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            desctiption = " - To enhance the security of LSASS and mitigate the risk of credential theft, activate Attack Surface Reduction (ASR) rules on Windows 10. <br /> - Consider disabling or restricting NTLM. <br /> - Enable Protected Process Light for LSA on Windows 8.1 and Windows Server 2012 R2 to enhance security."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Keep a close eye on executed commands and their associated arguments that could potentially try to access credential material stored in the process memory of the Local Security Authority Subsystem Service (LSASS). <br /> - Remain vigilant for API calls that could potentially aim to access credential material stored in the process memory of the Local Security Authority Subsystem Service (LSASS)."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))




        # sous-titre : T1053.002-At.exe Scheduled task

        activities = Activity.objects.filter(type="T1053.002-At.exe Scheduled task" ,user_id=request.user.id,
                                             workspace_id=session["workspace"],
                                             results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de T1053.002-At.exe Scheduled task qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                if "traitement" in activity.results:
                    verif = True
                    break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1053.002-At.exe Scheduled task"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : T1053.002-At.exe Scheduled task
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Adversaries have the potential to exploit the at utility, which allows for task scheduling, to carry out the initial or recurring execution of malicious code. The at utility is available as an executable on Windows, Linux, and macOS platforms, enabling the scheduling of tasks at specific times and dates."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : T1053.002-At.exe Scheduled task
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1


            for activity in activities:
                if activity.results != None and activity.results:
                    if "traitement" in activity.results:
                        if activity.results["traitement"]:
                            # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                            subtitle = activity.name
                            subtitle_style = styles["Heading4"]
                            story.append(Paragraph(subtitle, subtitle_style))

                            traitement = activity.results["traitement"]

                            description = traitement
                            story.append(Paragraph(description, paragraph_style))
                            story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : at
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - PowerSploit framework, among other toolkits, includes PowerUp modules that enable the exploration of systems to identify permission vulnerabilities within scheduled tasks. These weaknesses can potentially be exploited to elevate privileges. <br /> - Adjust the configuration settings for scheduled tasks to enforce the execution of tasks under the context of the authenticated account, rather than permitting them to run as SYSTEM."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Keep a vigilant watch on executed commands and their associated arguments for any actions that could be performed to create or modify tasks. <br /> - Stay alert for newly spawned processes that have command-lines involved in the creation/modification or execution of tasks."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))





        #--------------------------------------------------------------------------------------------------------------
        # -- > sous-titre : pass the hash:
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"], type="T1550.002 - Pass the hash", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de pass the hash qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1550.002 - Pass the hash"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : Pass the hash
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "By utilizing purloined password hashes, adversaries can engage in pass the hash techniques to traverse laterally within an environment, effectively bypassing standard system access controls. Pass the hash (PtH) refers to a method of authentication that enables adversaries to authenticate as a user without having access to the user's plaintext password"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : password cracking
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))


                    table_data = [[Paragraph('Username', paragraph_style), Paragraph('NTLM Hash', paragraph_style), Paragraph('Host ip', paragraph_style), Paragraph('Host name', paragraph_style), Paragraph('Pwn3d', paragraph_style),]]

                    for host in activity.results["hosts"]:
                        host["Pwn3d"] = str(host["Pwn3d"])

                        table_data.append([
                            Paragraph(activity.results["username"], paragraph_style), Paragraph(activity.results["hash_ntlm"], paragraph_style), Paragraph(host["host_ip"], paragraph_style), Paragraph(host["host_name"], paragraph_style), Paragraph(str(host["Pwn3d"]), paragraph_style),
                        ])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : password cracking
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- In order to prevent the negative consequences of credential compromise and minimize the adversary's capability to engage in Lateral Movement between systems, it is important to restrict the overlap of credentials across different systems. <br /> - Apply patch KB2871997 to Windows 7 and higher systems to limit the default access of accounts in the local administrator group <br /> - Ensure that a domain user is not granted membership in the local administrator group on multiple systems.<br />"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- Keep a close watch on recently established logins and credentials utilized in events, and carefully examine them for any inconsistencies. Any abnormal remote logins that coincide with other dubious actions, like the creation and execution of binaries, could potentially signify malicious activity. <br /> - Monitor for user authentication attempts."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))




        # -- > sous-titre : DCsync:
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1003.006 - Dcsync", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de dcsync qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1003.006 - Dcsync"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : dcsync
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Using a technique called DCSync, adversaries may abuse a Windows Domain Controller's application programming interface (API) to simulate the replication process from a remote domain controller, aiming to gain unauthorized access to credentials and other sensitive information."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : dcsync
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    table_data = [[Paragraph('Username', paragraph_style), Paragraph('RID', paragraph_style),
                                   Paragraph('LM Hash', paragraph_style), Paragraph('NTLM Hash', paragraph_style),
                                    ]]



                    for credential in activity.results["creds"]:


                        table_data.append([
                            Paragraph(credential["username"], paragraph_style),
                            Paragraph(credential["rid"], paragraph_style),
                            Paragraph(credential["lm_hash"], paragraph_style), Paragraph(credential["nt_hash"], paragraph_style),
                        ])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : DCSync
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- Take charge of the access control list for Replicating Directory Changes and other permissions related to domain controller replication <br /> - Ensure that local administrator accounts have complex, unique passwords across all systems on the network."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- Keep an eye on the logs of domain controllers to detect any replication requests or unexpected activities that might be linked to DCSync. <br /> - "
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))


        # silver ticket attack

        # -- > sous-titre : Silver tickets:
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1558.002 - Silver ticket", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de silver ticket qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1558.002 - Silver ticket"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : silver ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Service tickets, also referred to as Kerberos TGS tickets, can be forged by adversaries possessing the password hash of a target service account (such as SharePoint or MSSQL). These forged tickets are commonly known as silver tickets."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : silver ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1


            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    table_data = [[Paragraph('Ticket type', paragraph_style), Paragraph('Ticket path', paragraph_style),
                                   Paragraph('Ticket name', paragraph_style),
                                    ]]


                    table_data.append([
                        Paragraph(activity.results["ticket_type"], paragraph_style),
                        Paragraph(activity.results["ticket_path"], paragraph_style),
                        Paragraph(activity.results["ticket_name"], paragraph_style),
                    ])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : silver ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - Enable AES Kerberos encryption (or another stronger encryption algorithm), rather than RC4, where possible <br /> - To ensure the security of service accounts, it is important to enforce both a strong password length (preferably 25+ characters) and complexity, along with regular password expiration."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = " - It is essential to keep a vigilant eye out for abnormal Kerberos activity, including occurrences of malformed or empty fields in Windows logon/logoff events (Event ID 4624, 4634, 4672)."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

















        # Sous titre pour la technique forge golden ticket :

        # -- > sous-titre : Golden tickets:
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1558.001 - Golden ticket", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de dcsync qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1558.001 - Golden ticket"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : golden ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Having possession of the KRBTGT account password hash empowers adversaries to fabricate Kerberos ticket-granting tickets (TGT), commonly referred to as golden tickets. These golden tickets provide adversaries with the ability to produce authentication credentials for any account within the Active Directory system."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : golden ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    table_data = [[Paragraph('Ticket type', paragraph_style), Paragraph('Ticket path', paragraph_style),
                                   Paragraph('Ticket name', paragraph_style),
                                    ]]


                    table_data.append([
                        Paragraph(activity.results["ticket_type"], paragraph_style),
                        Paragraph(activity.results["ticket_path"], paragraph_style),
                        Paragraph(activity.results["ticket_name"], paragraph_style),
                    ])

                    # Calculer la largeur de chaque colonne
                    num_columns = len(table_data[0])
                    column_width = 500 / num_columns
                    # Création du tableau
                    table = Table(table_data, colWidths=[column_width])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > Recommendations pour la technique : golden ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- To mitigate the impact of a previously generated golden ticket, reset the built-in KRBTGT account password twice. This action will render any existing golden tickets created using the KRBTGT hash, as well as other Kerberos tickets derived from it, invalid."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- Monitor for anomalous Kerberos activity, such as malformed or blank fields in Windows logon/logoff events (Event ID 4624, 4634, 4672)."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))




        # -- > sous-titre : Pass the ticket :
        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"],
                                             type="T1550.003 - Pass the ticket", results__isnull=False)
        # on vérifie d'abord est ce qu'il y'a une activité de dcsync qui a un résultat
        verif = False
        for activity in activities:
            if activity.results != None and activity.results:
                verif = True
                break

        if verif == True:
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". T1550.003 - Pass the ticket"
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # -- > description de la technique : Pass the ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = "Adversaries have the ability to utilize stolen Kerberos tickets in order to perform lateral movement within an environment, bypassing regular system access controls. Pass the ticket (PtT) refers to the technique of authenticating to a system using Kerberos tickets, even without knowledge of the account's password. Kerberos authentication serves as the initial stage for executing lateral movement towards a remote system"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique : pass the ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            for activity in activities:
                if activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))
                    story.append(Spacer(1, 0.1 * inch))
                    if activity.results["ticket_path"]:
                        description = "Ticket path : " + activity.results["ticket_path"] + "<br /> Targeted service " + activity.results["Service"]
                        story.append(Paragraph(description, paragraph_style))
                        story.append(Spacer(1, 0.1 * inch))
                        table_data = [[Paragraph('Host ip', paragraph_style), Paragraph('Host name', paragraph_style),
                                       Paragraph('Pwn3d', paragraph_style),
                                       ]]


                        if len(activity.results["hosts"]) > 0:
                            for host in activity.results["hosts"]:


                                table_data.append([
                                    Paragraph(host["host_ip"], paragraph_style),
                                    Paragraph(host["host_name"], paragraph_style),
                                    Paragraph(str(host["Pwn3d"]), paragraph_style),
                                ])

                            # Calculer la largeur de chaque colonne
                            num_columns = len(table_data[0])
                            column_width = 500 / num_columns
                            # Création du tableau
                            table = Table(table_data, colWidths=[column_width])
                            table.setStyle(table_style)

                            story.append(table)
                            story.append(Spacer(1, 0.1 * inch))
                        else:
                            description = "The attempt to utilize the pass the ticket technique was unsuccessful."
                            story.append(Paragraph(description, paragraph_style))
                            story.append(Spacer(1, 0.1 * inch))



            # -- > Recommendations pour la technique : pass the ticket
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            subtitle = "Mitigations"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- In order to limit the effects of a previously generated golden ticket, it is advisable to reset the password of the built-in KRBTGT account twice. This action will render any existing golden tickets created with the KRBTGT hash, as well as other Kerberos tickets derived from it, invalid. <br /> - Limit domain admin account permissions to domain controllers and limited servers. Delegate other admin functions to separate accounts"
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            subtitle = "Detection"
            subtitle_style = styles["Heading4"]
            story.append(Paragraph(subtitle, subtitle_style))

            description = "- Keep a vigilant watch for recently observed logon patterns that could indicate the use of stolen Kerberos tickets for lateral movement within a given environment, thereby circumventing standard system access controls. <br /> - Perform a comprehensive audit of all events related to Kerberos authentication and the utilization of credentials, and carefully examine them to identify any inconsistencies or irregularities."
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))













        # Cette partie est reservé pour les technique de atomic red team :

        # on doit d'abord obtenir le nom de chaque technique de atomic red team qui a été utilisé

        activities = Activity.objects.filter(user_id=request.user.id, workspace_id=session["workspace"], results__isnull=False)
        banned = ["Network scan", "vuln scan", "Exploitation", "Ldap enumeration", "SMB enumeration", "T1110.002 - Password cracking", "T1550.002 - Pass the hash", "T1003.006 - Dcsync", "T1558.001 - Golden ticket", "T1550.003 - Pass the ticket", "Port listener", "T1003.002-Dump-SAM-With-Mimikatz", "T1003.005-Cached Credential Dump via Mimikatz", "T1003.001-Dump LSASS.exe Memory using ProcDump", "T1003.001-Dump LSASS.exe Memory using comsvcs.dll", "T1053.002-At.exe Scheduled task", "T1558.003 - Kerberoasting", "T1558.002 - Silver ticket", "T1574.011-Service Registry Permissions Weakness"]
        used_techniques = [] # Va contenir le nom de chaque technique qui est utilisé et qui est de atomic red team ( non implémenté par nous meme )
        for activity in activities:
            if activity.type not in banned and activity.type not in used_techniques and activity.results != None and activity.results:
                used_techniques.append(activity.type)

        print(used_techniques)

        for technique_name in used_techniques:
            # sous-titre pour cette activité :
            sub_subtitle_number[0] = sub_subtitle_number[0] + 1
            sub_subtitle_number[1] = 1

            subtitle = str(subtitle_number) + ". " + technique_name
            subtitle_style = styles["Heading2"]
            story.append(Paragraph(subtitle, subtitle_style))
            subtitle_number = subtitle_number + 1

            # rechercher une description pour cette technique :
            # obtenir d'abord l'id de la technique
            pattern = r'(T\d+(?:\.\d+)?)' #expression régulière pour récuperer l'id de la technique a partir de technique_name
            match = re.search(pattern, technique_name)
            technique_id = match.group(1)
            print("technique id -----> " + technique_id)

            # rechercher dans la bdd .json la description et les recommendations pour cette technique
            technique_recommendation_detection = ""
            technique_description = ""

            with open("My_app/info/entreprise-attack.json", "r") as fichier:
                data = json.load(fichier)
            # recherche de la technique parmis l'ensemble de technique
            for ttp in data["objects"]:
                if "external_references" in ttp:
                    if ttp["external_references"][0]["external_id"] == technique_id:
                        technique_description = ttp["description"].replace("\n", "<br />")
                        technique_recommendation_detection = ttp["x_mitre_detection"].replace("\n", "<br />")
                        break



            print("description ----------------> " + technique_description)
            print("----------------------------------------------")
            print(technique_recommendation_detection)
            # -- > description de la technique
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Description"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1

            description = technique_description
            story.append(Paragraph(description, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))

            # -- > résultats de la technique
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Results"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1


            for activity in activities:
                if activity.type == technique_name and activity.results != None and activity.results:
                    # On ajoute un sous titre contenant le nom de l'activité pour chaque activité
                    subtitle = activity.name
                    subtitle_style = styles["Heading4"]
                    story.append(Paragraph(subtitle, subtitle_style))

                    description = "Target -> " + activity.results["target_address"]
                    story.append(Paragraph(description, paragraph_style))
                    story.append(Spacer(1, 0.1 * inch))

                    table_data = [
                        # Titres des colonnes
                        ['Commands', 'results'],
                    ]

                    for command, val in activity.results["commands"].items():
                        table_data.append([Paragraph(command, paragraph_style), Paragraph(val.replace("\n", "<br />"), paragraph_style)])


                    # Création du tableau
                    table = Table(table_data, colWidths=[150, 350])
                    table.setStyle(table_style)

                    story.append(table)
                    story.append(Spacer(1, 0.1 * inch))

            # -- > recommendations pour la technique
            subtitle = str(sub_subtitle_number[0]) + "." + str(sub_subtitle_number[1]) + " Recommendations"
            subtitle_style = styles["Heading3"]
            story.append(Paragraph(subtitle, subtitle_style))
            sub_subtitle_number[1] = sub_subtitle_number[1] + 1


            story.append(Paragraph(technique_recommendation_detection, paragraph_style))
            story.append(Spacer(1, 0.1 * inch))


        # Créer le fichier ( mais dans ce cas c'est en mémoire pas sur le disque )
        doc.build(story)

        # Rembobinez le buffer pour permettre la lecture
        buffer.seek(0)

        report_buffer = buffer.getvalue()
        buffer.close()
        # Enregistrez le contenu du rapport dans la session
        encoded_content = base64.b64encode(report_buffer).decode('utf-8')
        request.session['report_buffer'] = encoded_content
        #report_content = request.session.get('report_content')


        return render(request, 'preview_report.html', {'pdf_content': encoded_content})



#-----------------------------------------------------------------------------------------------------------------------
def My_app_alerts(request):
    if "workspace" not in request.session:
        return redirect("My_app-attacks")

    return render(request, "activite/alerts.html", {})