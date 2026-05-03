import tornado.websocket
import tornado.ioloop
import tornado.web
import time
import json
from pymetasploit3.msfrpc import MsfRpcClient

class WSHandler(tornado.websocket.WebSocketHandler):

    def initialize(self):
    	self.client = MsfRpcClient('anis', ssl=True)

    	self.session_uuid = None
    	self.pwd = "$ "

    def check_origin(self, origin):
        # Allow connections from any origin, adjust accordingly
        return True
        
    def open(self): 
        print('WebSocket opened')
        
	
    def on_message(self, command):

        if "session uuid:" in command:
            self.session_uuid = command[13:]
        
        else:
            print('Received message:', command)
            # Do something with the command
        
            #creer un objet shell pour executer des commandes
            shell = self.client.sessions.session(self.session_uuid)
        
            #j'ai fait un time.sleep pour les commandes qui demmande de temps pour returner une resultat
            shell.write(command)
            time.sleep(2)
            resultat = shell.read()
            resultat = str(resultat)
            resultat = resultat.replace("\n", "\r\n")
            print(resultat)
        
            
            envoye = "\r\n"+resultat+"\r\n"+self.pwd+">"
        
            self.write_message(envoye)

    def on_close(self):
        print('WebSocket closed')

def make_app():
    return tornado.web.Application([
        (r'/websocket', WSHandler),
    ])

if __name__ == '__main__':
    try:
        app = make_app()
        app.listen(8006)
        tornado.ioloop.IOLoop.current().start()
    except:
        print("Programme deja lancé")
