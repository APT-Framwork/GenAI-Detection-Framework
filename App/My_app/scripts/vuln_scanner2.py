import sys
import xmltodict
from gvm.connections import UnixSocketConnection
from gvm.errors import GvmError
from gvm.protocols.gmp import Gmp
from gvm.transforms import EtreeCheckCommandTransform
from lxml import etree
from datetime import datetime
import time
from gvm.xml import pretty_print
import xmltodict
import json
import argparse
import sqlite3


# Les arguments :
parser = argparse.ArgumentParser()
parser.add_argument('--ip', type=str, required=True, help='Host ip to scan')
parser.add_argument('--activity_id', type=str, required=True, help='activity id')
args = parser.parse_args()

path = '/var/run/gvmd/gvmd.sock'
connection = UnixSocketConnection(path=path)
transform = EtreeCheckCommandTransform()

username = 'admin'
password = 'e37e240b-5b2b-446b-9faa-d62af82c0ea0'


with Gmp(connection=connection, transform=transform) as gmp:
    gmp.authenticate(username, password)
    
    
    # create target
    target_ipaddress = args.ip
    target_name = f"Suspect Host {target_ipaddress} {str(datetime.now())}"
    target_port_range = '20-600'
    target = gmp.create_target(name=target_name, hosts=[target_ipaddress], port_range=target_port_range)    

    # get the list of scan configurations
    #config_list = gmp.get_scan_configs()    

    # # find the ID of the configuration we want to use, c'est juste un affichage des IDs des scan configs    
    #for config in config_list:
    #    print(config.get('id'))

    config_id = 'daba56c8-73ec-11df-a475-002264764cea'

    # find the id of the scanner juste un affichage des id puis on choisis l'id
    #scanners = gmp.get_scanners() 

    #for scanner in scanners:
    #    print(scanner.get('id'))

    scanner_id = '08b69003-5fc2-4037-a479-93b440211c73'   


    # create task
    task_name = f"Task {str(datetime.now())}"
    task = gmp.create_task(name=task_name, config_id=config_id, target_id=target.get('id'), scanner_id=scanner_id)
    task_id = task.get('id')

    print(f"Task created with ID: {task.get('id')}")

    #start task
    report = gmp.start_task(task.get('id'))
    print(report.attrib)
    print("started scan of host " + str(args.ip) + ", corresponding report id is" + report[0].text)
    
    while True:
        task = gmp.get_task(task_id)
        status = task.find(".//status").text
        if status == "Done":
            #report_id = task.find("last_report").text
            resultat = gmp.get_report(report[0].text, ignore_pagination=True)
            #pretty_print(resultat)
            break
        time.sleep(10)    

        

    print("le type de resultat est : " + str(type(resultat)))
    resultat_dict = xmltodict.parse(etree.tostring(resultat))
    print("le type de resultat apres xmltodict est : " + str(type(resultat_dict)))
    resultat_json = json.dumps(resultat_dict)
    print("le type de resultat apres json.dumps est : " + str(type(resultat_json)))
    
    print('la tache a terminé')

    #Mise a jour du resultat dans la Base de donnee :

    # obtenir l'id de l'activite sur laquel on va enregistrer le resultat :
    activity_id = int(args.activity_id)

    # Se connecter a la BDD pour enregistrer le resultat sous format json :

    conn = sqlite3.connect("db.sqlite3")
    c = conn.cursor()

    activities = c.execute("update My_app_activity set results = ? where id = ?", (resultat_json, activity_id))
    activities = c.execute("update My_app_activity set end_date = ? where id = ?", (datetime.now(), activity_id))

    # commit les changements :
    conn.commit()

    # close database connection :
    conn.close()



