import stomp
import time
import json
import creds
import csv
import pickle

W  = '\033[0m'  # white (normal)
R  = '\033[31m' # red
G  = '\033[32m' # green
B =  '\033[34m' # blue

HOSTNAME = "datafeeds.networkrail.co.uk"
USERNAME = creds.USERNAME
PASSWORD = creds.PASSWORD
td_channel = "TD_ALL_SIG_AREA"
mvt_channel = "TRAIN_MVT_ALL_TOC"


train_ids = {}
try:
    filehandler = open("train_ids", 'rb') 
    train_ids = pickle.load(filehandler)
except:
    print ("couldn't load file")

service_codes = {}

line_count = 0

with open('./train_service_codes/service_codes.csv') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
        
    for row in csv_reader:
        if line_count == 0:
            print(f'Column names are {", ".join(row)}')
            line_count += 1
        else:
            service_codes[row[0]] = row[1]
            line_count += 1

class TDListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
    def on_message(self, headers, messages):
        #print(R+message)
        for message in json.loads(messages):
            
            if "CA_MSG" in message and message["CA_MSG"]["area_id"] in ["D9"] and message["CA_MSG"]["to"] in [ "2021", "2018"]: #2021 south 2018 north
                    print(B+ message)
                    try:
                        id = message["CA_MSG"]["descr"]
                        print(service_codes[train_ids[id]])
                    except:
                        print("didn't work")
            if json.dumps(message).find("2V64") > -1:
                print(R+str(message))
                try:
                    id = message["CA_MSG"]["descr"]
                    print(train_ids[id])
                    print(service_codes[train_ids[id]])
                except:
                    print("couldn't find train")
                
class MVTListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
    def on_message(self, headers, messages):
        #print(G+'received a message "%s"' % message)
        for message in json.loads(messages):
            msg = message['body']
            stanox_list = [
                msg['reporting_stanox'][0:2] if 'reporting_stanox' in msg else "00",
                msg['next_report_stanox'][0:2] if 'next_report_stanox' in msg else "00",
                msg['loc_stanox'][0:2] if 'loc_stanox' in msg else "00"
            ]
            
            if set(stanox_list).intersection(["68", "75", "81", "76"]) != set():
                train_ids[msg["train_id"][2:6]] = msg["train_service_code"]
                #print(G+"meow", msg["train_service_code"], msg["train_id"][2:6])
                filehandler = open("train_ids", 'wb') 
                pickle.dump(train_ids, filehandler)

td_conn = stomp.Connection(host_and_ports=[(HOSTNAME, 61618)])
td_conn.set_listener('', TDListener())
td_conn.start()
td_conn.connect(username=USERNAME, passcode=PASSWORD)
td_conn.subscribe(destination=f"/topic/{td_channel}", id=1, ack='auto')

mvt_conn = stomp.Connection(host_and_ports=[(HOSTNAME, 61618)])
mvt_conn.set_listener('', MVTListener())
mvt_conn.start()
mvt_conn.connect(username=USERNAME, passcode=PASSWORD)
mvt_conn.subscribe(destination=f"/topic/{mvt_channel}", id=1, ack='auto')

time.sleep(1000)
td_conn.disconnect()
mvt_conn.disconnect()

