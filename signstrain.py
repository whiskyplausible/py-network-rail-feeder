## TODO
## Reset if lost network or stomp connection
## Read only sd card (prob needs USB)
## Remember to wipe the train ids thingy array every midnight

import stomp
import json
import time
import creds
import csv 

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

train_fake = [False, False, False, False]

print("time ", time.process_time())

train_ids = {}
# try:
#     filehandler = open("train_ids", 'rb') 
#     train_ids = pickle.load(filehandler)
# except:
#     print ("couldn't load file")

service_codes = {}


class TDListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
    def on_message(self, headers, messages):
        global train_fake, train_text, train_last_seen, train_change, show_trains

        for message in json.loads(messages):

            if time.perf_counter() - start_time > 5 and not train_fake[0]:
                train_fake[0] = True
                print("faking a train!")
                message = {
                    "CA_MSG": {
                        "area_id": "D9",
                        "to": "2018",
                        "descr": "0101"
                    }
                }

            if time.perf_counter() - start_time > 10 and not train_fake[2]:
                train_fake[2] = True
                print("faking a train!")
                message = {
                    "CA_MSG": {
                        "area_id": "D9",
                        "to": "2021",
                        "descr": "aaaa"
                    }
                }

            if "CA_MSG" in message and message["CA_MSG"]["area_id"] in ["D9"] and message["CA_MSG"]["to"] in [ "2021", "2018"]: #2021 south 2018 north
                show_trains = True
               
                #print(B+ str(message))
                id = message["CA_MSG"]["descr"]
                try:
                    service_id = service_codes[train_ids[id]]
                except:
                    service_id = id # show service code here too if poss?

                if message["CA_MSG"]["to"] == "2021":
                    train_text[1] = service_id
                    train_last_seen[1] = time.perf_counter() - start_time
                else:
                    train_text[0] = service_id
                    train_last_seen[0] = time.perf_counter() - start_time

                train_change = True

            if time.perf_counter() - start_time > 20 and not train_fake[1]:
                train_fake[1] = True
                print("faking a train!")
                message = {
                    "CA_MSG": {
                        "area_id": "D9",
                        "to": "2016",
                        "descr": "0101"
                    }
                }


            if time.perf_counter() - start_time > 30 and not train_fake[3]:
                train_fake[3] = True
                print("faking a train!")
                message = {
                    "CA_MSG": {
                        "area_id": "D9",
                        "to": "2023",
                        "descr": "aaaa"
                    }
                }

            if "CA_MSG" in message and message["CA_MSG"]["area_id"] in ["D9"] and message["CA_MSG"]["to"] in [ "2023", "2016"]: #train has passed by now
                if message["CA_MSG"]["to"] == "2023":
                    train_text[1] = ""
                    train_last_seen[1] = 0
                    print("train has passed south")
                else:
                    train_text[0] = ""
                    train_last_seen[0] = 0
                    print("train has passed north")

                if train_text[0] == "" and train_text[1] == "":
                    show_trains = False

                train_change = True

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
                #filehandler = open("train_ids", 'wb') 
                #pickle.dump(train_ids, filehandler)

def make_connections():
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

    #return [td_conn, mvt_conn]

line_count = 0

with open('./train_service_codes/service_codes.csv') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
        
    for row in csv_reader:
        if line_count == 0:
            line_count += 1
        else:
            service_codes[row[0]] = row[1]
            line_count += 1

make_connections()

while 1:
    if show_trains and current_display != "TRAINS":
        current_display = "TRAINS"
        print("showing trains", train_text)


    if not show_trains and current_display == "TRAINS":
        current_display = "BLANK"
        print("display off")

    if train_change and show_trains:
        train_change = False
        print("train approaching")
        print(train_text)

    if train_change and not show_trains:
        train_change = False   
        print("train has now passed by")

    if train_text[0] and train_last_seen[0] + 300 < time.perf_counter() - start_time:
        train_text[0] = ""
        train_last_seen[0] = 0
        print("north bound train time out")

    if train_text[1] and train_last_seen[1] + 300 < time.perf_counter() - start_time:
        train_text[1] = ""
        train_last_seen[1] = 0
        print("south bound train time out")

    if train_text[0] == "" and train_text[1] == "":
        show_trains = False

    time.sleep(1)