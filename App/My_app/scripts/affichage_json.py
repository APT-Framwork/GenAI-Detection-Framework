import json
from pprint import pprint
import sqlite3

# obtenir l'id de l'activite sur laquel on va enregistrer le resultat :
activity_id = 56

# Se connecter a la BDD pour enregistrer le resultat sous format json :

conn = sqlite3.connect("/home/anis/Documents/PFE/ART/db.sqlite3")
c = conn.cursor()

resultat_json = c.execute("select results from My_app_activity where id=?", (activity_id,)).fetchall()[0]
#resultat_dict = json.loads(resultat_json)

pprint(resultat_json)

# close database connection :
conn.close()
