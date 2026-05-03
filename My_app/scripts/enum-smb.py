import nmap 
import argparse
import json
import sqlite3
from datetime import datetime

#Les arguments :
#remarque : decommenté les arguments
parser = argparse.ArgumentParser()

parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--address', type=str, required=True, help='ip address')

args = parser.parse_args()

ipaddr = args.address
activity_id = args.activity_id

ports = '139,445'
args = '-sV --script smb-os-discovery.nse,smb-security-mode.nse,smb2-security-mode.nse'

#Creer un Objet nmap
nm = nmap.PortScanner()

#Lancer l'énumeration SMB
nm.scan(ipaddr, ports, args)
# Parcourir les résultats du scan

resultats = {}

#j'ai declarer les variables ici pour ne pas avoire des erreurs par la suite si les ports 139 et 445 sont fermer ou filtrer


for host in nm.all_hosts():
    resultat_host = {}
    host_ip = ''
    host_mac_addr = ''
    fqdn = ''
    workgroup = ''
    os = ''
    computer_name = ''
    smb_authentication_level = ''
    smb_challenge_response = ''
    smb_signature = ''
    smb_v2_signature = ''
    isvm = ''

    host_ip = nm[host]['addresses']['ipv4']

    if "mac" in nm[host]['addresses']:
        host_mac_addr = nm[host]['addresses']['mac']
        isvm = False
        #verifier si la machine enumerer est une machine virtuelle ou pas?
        if nm[host]['vendor'][host_mac_addr] == 'VMware':
            isvm = True
    
    port_139_infos = {}
    state_139 = nm[host]['tcp'][139]['state']
    service_139 = nm[host]['tcp'][139]['name']
    version_139 = nm[host]['tcp'][139]['product']

    port_139_infos ={
            'state' : state_139,
            'service' : service_139,
            'service version' : version_139

            }
    port_445_infos = {}
    state_445 = nm[host]['tcp'][445]['state']
    service_445 = nm[host]['tcp'][445]['name']
    version_445 = nm[host]['tcp'][445]['product']

    port_445_infos = {
            'state' : state_445,
            'service' : service_445,
            'service version' : version_445

            }
    #rajouter une condition pour dire si les ports 139 et 445 ne sont pas open alors ne faire pas la boucle for qui suite
    if state_139 == 'open' and state_445 == 'open':

        fqdn = ''
        workgroup = ''
        for script in  nm[host]['hostscript']:

            if script['id'] == 'smb-os-discovery':
                script_output_list = script['output'].split('\n')

                for ligne_resultat in script_output_list:
                    if ligne_resultat.split(':')[0] == '  OS':
                        os = ligne_resultat.split(':')[1]
                    elif ligne_resultat.split(':')[0] == '  Computer name':
                        computer_name = ligne_resultat.split(':')[1]
                    elif ligne_resultat.split(':')[0] == '  FQDN':
                        fqdn = ligne_resultat.split(':')[1]
                    elif ligne_resultat.split(':')[0] == '  Workgroup':
                        workgroup = ligne_resultat.split(':')[1].replace('\\x00','')
                    
            

                #if script['output'].split('\n')[5].replace('\\x00','').split(':')[0] == '  Workgroup':
                    # workgroup = script['output'].split('\n')[5].replace('\\x00','').split(':')[1]
                #else:
                    #fqdn = script['output'].split('\n')[5].replace('\\x00','').split(':')[1]
            elif script['id'] == 'smb-security-mode':
                smb_authentication_level = script['output'].split('\n')[2].split(':')[1]
                smb_challenge_response = script['output'].split('\n')[3].split(':')[1]
                smb_signature = script['output'].split('\n')[4].split(':')[1]
            else:
                smb_v2_signature = script['output'].split('\n')[2]
    
    resultat_host = {
            'host_ip' : host_ip,
            'mac_addr' : host_mac_addr,
            'virtuelle_machine' : isvm,
            'port_139_infos' : port_139_infos,
            'port_445_infos' : port_445_infos,
            'FQDN' : fqdn,
            'workgroup' : workgroup,
            'OS' : os,
            'computer_name' : computer_name,
            'smb_authentication_level' : smb_authentication_level,
            'smb_challenge_response' : smb_challenge_response,
            'smb_signature' : smb_signature,
            'smb_v2_signature' : smb_v2_signature

            }
    resultats[host] = resultat_host



print(resultats)

#transformer le dictionnaire en JSON
json_resultats = json.dumps(resultats)

# obtenir l'id de l'activite sur laquel on va enregistrer le resultat :
activity_id = int(activity_id)

# Se connecter a la BDD pour enregistrer le resultat sous format json :
conn = sqlite3.connect("db.sqlite3")
c = conn.cursor()

activities = c.execute("update My_app_activity set results = ? where id = ?", (json_resultats, activity_id))
activities = c.execute("update My_app_activity set end_date = ? where id = ?", (datetime.now(), activity_id))

# commit les changements :
conn.commit()

# close database connection :
conn.close()

