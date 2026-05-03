#importer les bibliothèques
import subprocess
import time
import argparse
import json
import sqlite3
from datetime import datetime

#Les arguments :
#remarque : decommenté les arguments
parser = argparse.ArgumentParser()

#parser.add_argument('--name', type=str, required=True, help='crack password name')
parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--hash_type', type=str, required=True, help='type de hashage')
parser.add_argument('--hash_value', type=str, required=True, help='la valeur de hash')
parser.add_argument('--wordlist_path', type=str, required=False, help='wordlist path')

args = parser.parse_args()

with open('hashfile.txt', 'w') as fichier:
    fichier.write(args.hash_value)
    #fichier.write('Administrateur:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::')

# Chemin d'accès complet vers le fichier contenant les mots de passe à casser
password_file = "hashfile.txt" 

#chemin d'accèes complet vers le fichier contenant la wordlist des password a testé
#wordlist = '/home/anis/scripts_bounouala/script_crackage/rockyou.txt'
#wordlist = None
wordlist = args.wordlist_path

#si le path vers la wordlist est mentionné
if wordlist is not None:
    cmd = "john --wordlist=" + wordlist + " --format=" + args.hash_type + " "  + password_file
    #cmd = "john --wordlist=" + wordlist + " --format=nt " + password_file

#sinon utilisé la wordlist par defaut de john
else:
    cmd = "john --format=" + args.hash_type + " " + password_file
    #cmd = "john --format=nt " + password_file


# Exécute la commande dans un nouveau processus
process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)


# Attend que la tâche soit terminée et récupère la sortie
output, error = process.communicate()

print("%%---------affichage sortie de premiere commande-----------%%")
print(output.decode("utf-8"))

# Affiche la sortie 
cmd = "john --show --format=" + args.hash_type  + " " + password_file
#cmd = "john --show --format=nt " + password_file

process1 = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
output1, error1 = process1.communicate()
print("%%-----affichage sortie de la dexieme commande---------------------%%")
print(output1.decode("utf-8"))

lignes = output1.decode("utf-8").split('\n')
print(lignes)

craque_val=lignes[-2].split(' ')[0]
print('craque_val : ' + craque_val)

#la variable erreur_type est utilisé afin d'affiché par exemple un message d'erreur dans l'interface web si le user choisit un type de hash erroné
erreur_type = lignes[-2].split(' ')[4]
print('erreur_type : '+ erreur_type)
if craque_val == '0':
    crack = False
else:
    crack = True

if erreur_type == '0'and craque_val == '0':
    erreur_hash_type=True
else:
    erreur_hash_type=False

username = ''
password = ''

if crack:
    for i in range(3):
        del lignes[-1]
    

    for ligne in lignes:
        username = ligne.split(':')[0]
        password = ligne.split(':')[1]

        print("Username : " + username + "\n" + "Password : " + password)


resultats = {
        'crack_stat' : str(crack),
        'username' : username,
        'password' : password,
        #'valeur de hash' : args.hash_value,
        'error_hash_type' : erreur_hash_type,
        'hash_value': args.hash_value,
        'hash_type': args.hash_type,
        }

if args.hash_type == "krb5tgs":
    resultats["kerberos_ticket"] = "yes"
    if crack == True:
        # calculer le hash du password
        cmd = "mkpasswd --method=nt " + password
        process1 = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        output1, error1 = process1.communicate()
        lignes = output1.decode("utf-8").split('\n')
        ntlm_hash = lignes[0][4:]
        resultats["service_ntlm_hash"] = ntlm_hash
else:
    resultats["kerberos_ticket"] = "no"



print(resultats)

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

# close database connection :
conn.close()
