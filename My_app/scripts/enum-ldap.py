import ldap3
import argparse
import json
import sqlite3
from datetime import datetime

#Les arguments :
#remarque : decommenté les arguments
parser = argparse.ArgumentParser()

parser.add_argument('--activity_id', type=str, required=True, help='activity id')
parser.add_argument('--address', type=str, required=True, help='ip address domain controller')
parser.add_argument('--username', type=str, required=True, help='utilisateur de domaine')
parser.add_argument('--password', type=str, required=True, help='mot de passe')
parser.add_argument('--domain_name', type=str, required=True, help='Domain name')
args = parser.parse_args()


#se connecter au serveur ldap
server = ldap3.Server('ldap://' + args.address)

try:
    conn = ldap3.Connection(server, args.username, args.password, auto_bind=True)
    #rajouter une condition pour dir si conn contient True c'est a dire connexion avec succes alors faire la suite sinon on va pas envoyé les requetes parce que on va avoire une erreur dans le programme !!! -->remarque critique
    dc = args.domain_name.split('.')[0]
    dc_suite = args.domain_name.split('.')[1]
    base_dn = 'dc=' + dc + ',dc=' + dc_suite

    print('%%----Controleurs de domaine----%%')
    #pour rechercher tout les controleurs de domaine
    search_filter = '(userAccountControl:1.2.840.113556.1.4.803:=8192)'
    #pour mentionné les attributs a recuperer
    attributes = ['name','operatingSystem','dNSHostName']
    #envoyé la requete de recherche au controleur de domaine
    conn.search(search_base=base_dn, search_filter=search_filter, attributes=attributes)

    domain_controlers=[]
    for entry in conn.entries:
        print(entry)

        domain_controler = {
                'name' : entry.name.value,
                'operating_system': entry.operatingSystem.value,
                'dns_host_name': entry.dNSHostName.value


         }
        domain_controlers.append(domain_controler)

    print(domain_controlers)

    print('%%----administrateur de domaine-----------%%')
    #pour rechercher tout les administrateurs de domaine
    search_filter = '(&(objectClass=user)(objectCategory=person)(memberOf=CN=Administrateurs,CN=Builtin,DC=' + dc + ',DC=' + dc_suite + '))'
    attributes = ['name', 'distinguishedName', 'mail']

    conn.search(search_base=base_dn, search_filter=search_filter, attributes=attributes)
    domain_admins = []

    for entry in conn.entries:
        print(entry)

        domain_admin = {
                'name' : entry.name.value,
                'distinguishedName' : entry.distinguishedName.value,
                'mail' : entry.mail.value

                }
        domain_admins.append(domain_admin)

    print(domain_admins)

    print('%%------Utilisateurs de domaine----%%')
    #pour rechercher tout les utilisateurs de domaine
    search_filter = '(&(objectClass=user)(objectCategory=person))'
    attributes = ['name','userPrincipalName','mail','description','memberOf']

    conn.search(search_base=base_dn, search_filter=search_filter, attributes=attributes)
    domain_users = []

    for entry in conn.entries:
        print(entry)

        domain_user = {
                'name' : entry.name.value,
                'user_principal_name' : entry.userPrincipalName.value,
                'mail' : entry.mail.value,
                'description' : entry.description.value,
                'membre_de' : entry.memberOf.value

                }
        domain_users.append(domain_user)

    print(domain_users)

    resultats = {
            'domain_controllers' : domain_controlers,
            'domain_admins' : domain_admins,
            'domain_users' : domain_users,
            'enumerated_machine' : args.address,

            }

except:
    resultats = {}


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

