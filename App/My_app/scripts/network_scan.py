import nmap
import argparse
import json
import sqlite3
from datetime import datetime


# Les arguments :


parser = argparse.ArgumentParser()
parser.add_argument('--name', type=str, required=True, help='Scan name')
parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--address', type=str, required=True, help='ip address')
parser.add_argument('--port', type=str, required=False, help='Port list')
parser.add_argument('--scan_type', type=str, required=False, help='scan type')
parser.add_argument('--service_version', type=str, required=False, help='Service version')
parser.add_argument('--os', type=str, required=False, help='Os discovery', action='store')

args = parser.parse_args()

# Créer un objet nmap
nm = nmap.PortScanner()

# Gerer les argumetns :

arguments = ""
if args.scan_type is not None:
    if args.scan_type == "half_open_scan":
        arguments = arguments + "-sS "
    elif args.scan_type == "full_open_scan":
        arguments = arguments + "-sT "
    elif args.scan_type == "xmas_scan":
        arguments = arguments + "-sX "
    elif args.scan_type == "udp_scan":
        arguments = arguments + "-sU "
    elif args.scan_type == "ack_scan":
        arguments = arguments + "-sA "

if args.os == 'True':
    arguments = arguments + "-O "

if args.service_version == 'True':
    arguments = arguments + "-sV "

if args.port is not None:
    port = args.port
else:
    port = None

# Lancer un scan sur une adresse IP
nm.scan(args.address, port, arguments)

# Parcourir les résultats du scan
resultats = {}
for host in nm.all_hosts():
    resultat_host = {}
    ports = {}
    os_matches = {}

    if args.os == 'True':

        if 'osmatch' in nm[host]:
            for osmatch in nm[host]['osmatch']:
                os_match = {
                    'osmatch_accuracy': osmatch['accuracy'],
                    'osmatch_line': osmatch['osclass'][0]['osfamily'],
                }
                os_matches[osmatch['name']] = os_match

    for proto in nm[host].all_protocols():
        lport = nm[host][proto].keys()
        for port in lport:
            port_info = {
                'status': nm[host][proto][port]['state'],
                'protocol': proto,
                'service': nm[host][proto][port]['name'],
                'version': nm[host][proto][port]['product'],
            }
            ports[port] = port_info

    resultat_host = {
        'os': os_matches,
        'port': ports,
        'hostname': nm[host].hostname(),
        'state': nm[host].state(),
    }

    resultats[host] = resultat_host

print(resultats)

# Transformer le dictionnaire en JSON :
json_resultats = json.dumps(resultats)

# obtenir l'id de l'activite sur laquel on va enregistrer le resultat :
activity_id = int(args.activity_id)

# Se connecter a la BDD pour enregistrer le resultat sous format json :

conn = sqlite3.connect("db.sqlite3")
c = conn.cursor()

activities = c.execute("update My_app_activity set results = ? where id = ?", (json_resultats, activity_id))
activities = c.execute("update My_app_activity set end_date = ? where id = ?", (datetime.now(), activity_id))

# commit les changements :
conn.commit()

# close database connection :
conn.close()