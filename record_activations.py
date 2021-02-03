## TODO
## Reset if lost network or stomp connection
## Read only sd card (prob needs USB)
## Remember to wipe the train ids thingy array every midnight
## If train not identified maybe show both IDs (at the moment just shows headcode)
## will that perf counter thing ever run out? Probs not.
## Show weather or whatever other stuff when no train things happening...
## Update script
## Train IDs still not quite there maybe, that Birmingham Service?

import stomp
import json
import time
import creds
import csv 
import logging
import datetime

dev = False

logging.basicConfig(
    filename='activations.log', filemode='a',
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.CRITICAL,
    datefmt='%Y-%m-%d %H:%M:%S')

HOSTNAME = "datafeeds.networkrail.co.uk"
USERNAME = creds.USERNAME
PASSWORD = creds.PASSWORD
td_channel = "TD_ALL_SIG_AREA"
mvt_channel = "TRAIN_MVT_ALL_TOC"

start_time = time.perf_counter()
show_trains = False
train_last_seen = [0,0]
train_text = ["", ""]
train_change = False
current_display = "BLANK"
last_td_message = start_time
last_mvt_message = start_time

train_fake = [False, False, False, False]

print("time ", time.process_time())

train_ids = {}
# try:
#     filehandler = open("train_ids", 'rb') 
#     train_ids = pickle.load(filehandler)
# except:
#     print ("couldn't load file")

activations = {}

class MVTListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in MVTListener "+str(message))
    def on_message(self, headers, messages):
        global last_mvt_message
        last_mvt_message = time.perf_counter()
        #print(G+'received a message "%s"' % message)
        for message in json.loads(messages):
            if message['header']['msg_type'] == "0001": # this will look up all train activations and find the exact uid and trust id of our train
                msg = message['body']
                print(msg['train_id'])
                print("uid", msg['train_uid'])

                activations[msg['train_id']] = {
                    "train_uid": msg['train_uid'],
                    "train_service_code": msg['train_service_code']
                }

                filehandler = open("activations", 'w') 
                filehandler.write(json.dumps(activations, indent=4))
                filehandler.close()
                #filehandler = open("train_ids", 'wb') 
                #pickle.dump(train_ids, filehandler)
                if str(msg['train_service_code']) == "22180008":
                    filehandler = open("found_service_code.txt", 'w') 
                    filehandler.write(json.dumps(msg, indent=4))
                    filehandler.close()
                    

def make_connections():
    print("reset connections")
    logging.critical("resetting connections") 

    mvt_conn = stomp.Connection(host_and_ports=[(HOSTNAME, 61618)])
    mvt_conn.set_listener('', MVTListener())
    mvt_conn.start()
    mvt_conn.connect(username=USERNAME, passcode=PASSWORD)
    mvt_conn.subscribe(destination=f"/topic/{mvt_channel}", id=1, ack='auto')

make_connections()

while 1:

    time.sleep(1)