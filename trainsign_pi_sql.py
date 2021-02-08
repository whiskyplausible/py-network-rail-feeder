## TODO
## Write protect SD card
## Turn off disk logging.
## some external logging?!
## Dim status LEDs - maybe move to bottom of screen?

import pickle
import stomp
import json
import time
import creds
import csv 
import logging
import datetime
import os
import socket
import requests
import traceback
import _thread
from requests.auth import HTTPBasicAuth 
#import mysql.connector as mysql

dev = False
useDisk = False

if not dev:
    from samplebase import SampleBase
    from rgbmatrix import graphics

logging.basicConfig(
    filename='trains.log', filemode='a',
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
train_uids = {}
activations = {}
service_codes = {}
mvt_led = False
td_led = False
api_led = False
internet_on = False

if useDisk:
    try:
        filehandler = open("activations", 'rb') 
        activations = pickle.load(filehandler)
        filehandler.close()
        #print(activations)
    except:
        print ("couldn't load file: activations")

    try:
        filehandler = open("train_ids", 'rb') 
        train_ids = pickle.load(filehandler)
        filehandler.close()
        #print(activations)
    except:
        print ("couldn't load file: train_ids")

    try:
        filehandler = open("train_uids", 'rb') 
        train_uids = pickle.load(filehandler)
        filehandler.close()
        #print(activations)
    except:
        print ("couldn't load file: train_uids")

# db = mysql.connect(
#     host = "localhost",
#     user = "nikhil",
#     passwd = "Bd75W*0p1hB",
#     database = "trains"
# )
# cursor = db.cursor()

def internet(host="8.8.8.8", port=53, timeout=3):
    """
    Host: 8.8.8.8 (google-public-dns-a.google.com)
    OpenPort: 53/tcp
    Service: domain (DNS/TCP)
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error as ex:
        print(ex)
        return False

class RunText(SampleBase): #SampleBase):
    def __init__(self, *args, **kwargs):
        print("init")
        super(RunText, self).__init__(*args, **kwargs)
        self.parser.add_argument("-t", "--text", help="The text to scroll on the RGB LED panel", default="Hello world!")

    def run(self):
        print("starting")
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        font = graphics.Font()
        font.LoadFont("../../../fonts/7x13.bdf")
        timeFont = graphics.Font()
        timeFont.LoadFont("../../../fonts/6x10.bdf")
        posN = offscreen_canvas.width
        posS = offscreen_canvas.width
        
        brightness = 0
        while True:
            dirColor = graphics.Color(0,0,brightness)
            redColor = graphics.Color(255,0,0)
            textColor = graphics.Color(brightness, brightness, 0)

            now = datetime.datetime.now()
            timeNow = now.strftime('%H:%M:%S')
            offscreen_canvas.Clear()

            lenN = graphics.DrawText(offscreen_canvas, font, posN, 10, textColor, train_text[0])
            lenS = graphics.DrawText(offscreen_canvas, font, posS, 21, textColor, train_text[1])

            posN -= 1
            if (posN + lenN < 35):
                posN = offscreen_canvas.width

            posS -= 1
            if (posS + lenS < 35):
                posS = offscreen_canvas.width

            for box in range(0,21):
                graphics.DrawLine(offscreen_canvas,0,box, 35,box,graphics.Color(0,0,0))

            graphics.DrawText(offscreen_canvas, font, 0, 10, dirColor, "NORTH")
            graphics.DrawText(offscreen_canvas, font, 0, 21, dirColor, "SOUTH")
            graphics.DrawText(offscreen_canvas, timeFont, 72, 30, redColor, timeNow)

            if td_led:
                graphics.DrawLine(offscreen_canvas,0,0,0,0,graphics.Color(255,0,0))

            if mvt_led:
                graphics.DrawLine(offscreen_canvas,1,0,1,0,graphics.Color(0,0,255))

            if api_led:
                graphics.DrawLine(offscreen_canvas,2,0,2,0,graphics.Color(0,255,0))

            if brightness < 251:
                brightness+=4
            time.sleep(0.05)

            if not internet_on:
                graphics.DrawText(offscreen_canvas, timeFont, 72, 15, redColor, "No internet")
                
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

def check_internet():
    global internet_on
    while 1:
        i_check = internet()
        if not i_check:
            time.sleep(5)
            internet_on = internet()
        else:
            internet_on = True
        time.sleep(30)

def lookup_by_uid(uid):
    time_now = datetime.datetime.now()
    time_url = time_now.strftime("/%Y/%m/%d")
    url = "http://api.rtt.io/api/v1/json/service/"+str(uid).lstrip()+time_url
    #print("rtt url: ", url)
    try:
        req = requests.get(url, auth = HTTPBasicAuth(creds.RTT_USER, creds.RTT_PASS))
        #print("received lookup back from rtt", req.text)
        api_led = False
        if req.status_code != 200:
            api_led = True
        return req.json()

    except Exception as e: 
        print(e)        
        api_led = True

    return None

class TDListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in TDListener "+str(message))
    def on_message(self, headers, messages):
        global train_fake, train_text, train_last_seen, train_change, show_trains, last_td_message, td_led
        td_led = not td_led
        last_td_message = time.perf_counter()
        try:
            #print(".", end='', flush=True)
            for message in json.loads(messages):
                
                # if time.perf_counter() - start_time > 5 and not train_fake[0]:
                #     train_fake[0] = True
                #     #print("faking a train!")
                #     message = {
                #         "CA_MSG": {
                #             "area_id": "D9",
                #             "to": "2018",
                #             "descr": "0101"
                #         }
                #     }

                # if time.perf_counter() - start_time > 10 and not train_fake[2]:
                #     train_fake[2] = True
                #     #print("faking a train!")
                #     message = {
                #         "CA_MSG": {
                #             "area_id": "D9",
                #             "to": "2021",
                #             "descr": "aaaa"
                #         }
                #     }

                if "CA_MSG" in message and message["CA_MSG"]["area_id"] in ["D9"] and message["CA_MSG"]["to"] in [ "2021", "2018"]: #2021 south 2018 north
                    show_trains = True
                    
                    id = message["CA_MSG"]["descr"]
                    service_id = id                    
                    logging.critical("Train arrived at monitored berths. "+ str(message))

                    if id in train_ids and train_ids[id] in service_codes:
                        service_id = service_codes[train_ids[id]]
                        print("service code found in csv ", id, service_id)
                    else:
                        print("found id in csv service codes: ", train_ids[id])

                    if id in train_uids:
                        print("Found id in train_uids, trying api lookup")
                        try:
                            train_lookup = lookup_by_uid(train_uids[id])
                            print("match from lookup by uid origin: ",train_lookup["origin"][0]["description"]+" dest: "+ train_lookup["destination"][0]["description"])

                            service_id = train_lookup["atocName"]  + " [" + train_lookup['powerType'] + "] "
                            service_id += train_lookup["origin"][0]["description"]+" to "+ train_lookup["destination"][0]["description"]
 
                        except Exception:
                            print("train lookup failed: ", traceback.format_exc())

                    id_type = "?"
                    if id[0] == "1":
                        id_type = "High speed passenger"
                    if id[0:2] == "1Q":
                        id_type = "Test train"
                    if id[0:2] == "1Z":
                        id_type = "Charter"
                    if id[0] == "2":
                        id_type = "Slow passenger"
                    if id[0] == "3":
                        id_type = "Priority ECS/parcels/weather related"
                    if id[0] == "4":
                        id_type = "Fast freight"
                    if id[0] == "5":
                        id_type = "Empty passenger stock"
                    if id[0] == "6":
                        id_type = "Slow aggregates freight"
                    if id[0] == "7":
                        id_type = "Very slow freight"
                    if id[0] == "8":
                        id_type = "Weather related/very slow"
                    service_id += " (" + id_type + ")"

                    if message["CA_MSG"]["to"] == "2021":
                        train_text[1] = service_id
                        train_last_seen[1] = time.perf_counter() 
                    else:
                        train_text[0] = service_id
                        train_last_seen[0] = time.perf_counter() 

                    train_change = True

                # if time.perf_counter() - start_time > 20 and not train_fake[1]:
                #     train_fake[1] = True
                #     #print("faking a train!")
                #     message = {
                #         "CA_MSG": {
                #             "area_id": "D9",
                #             "to": "2016",
                #             "descr": "0101"
                #         }
                #     }


                # if time.perf_counter() - start_time > 30 and not train_fake[3]:
                #     train_fake[3] = True
                #     #print("faking a train!")
                #     message = {
                #         "CA_MSG": {
                #             "area_id": "D9",
                #             "to": "2023",
                #             "descr": "aaaa"
                #         }
                #     }

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
        
        except:
            logging.critical("this is an exception", exc_info=True) 
            print("error in td loop: ", traceback.format_exc())

class MVTListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in MVTListener "+str(message))
    def on_message(self, headers, messages):
        global last_mvt_message, activations, train_ids, train_uids, activations, mvt_led
        mvt_led = not mvt_led
        last_mvt_message = time.perf_counter()
        #print(G+'received a message "%s"' % message)
        for message in json.loads(messages):
            msg = message['body']
            if message['header']['msg_type'] == "0001": # this will look up all train activations and find the exact uid and trust id of our train
                activations[msg['train_id']] = {
                    "train_uid": msg['train_uid'],
                    "train_service_code": msg['train_service_code']
                }
                #print("adding this to actiations ", msg['train_id'])
                if useDisk:
                    filehandler = open("activations", 'wb') 
                    pickle.dump(activations, filehandler)
                    filehandler.close()

            stanox_list = [
                msg['reporting_stanox'][0:2] if 'reporting_stanox' in msg else "00",
                msg['next_report_stanox'][0:2] if 'next_report_stanox' in msg else "00",
                msg['loc_stanox'][0:2] if 'loc_stanox' in msg else "00"
            ]
            
            if set(stanox_list).intersection(["68", "75", "81", "76"]) != set():
                #logging.critical("found a relevant service "+str(msg))
                train_ids[msg["train_id"][2:6]] = msg["train_service_code"]
                if useDisk:
                    filehandler = open("train_ids", 'wb') 
                    pickle.dump(train_ids, filehandler)
                    filehandler.close()

                if msg["train_id"] in activations:
                    train_uids[msg["train_id"][2:6]] = activations[msg["train_id"]]["train_uid"]
                    #print("added detected train_uid: ", msg["train_id"][2:6])
                    if useDisk:
                        filehandler = open("train_uids", 'wb') 
                        pickle.dump(train_uids, filehandler)
                        filehandler.close()

                    #print("successful train id")
                else:
                    print("couldn't find key ", msg["train_id"], " in activations...")
                    pass


                # #print("train_id is ", msg["train_id"])
                # query = "SELECT train_uid, train_service_code FROM activations WHERE train_id = %s"
                # cursor.execute(query, (str(msg["train_id"]),))
                # records = cursor.fetchall()
                # for record in records:
                #     #print("found a match in sql: ", record[0], record[1], "for this id: "+msg["train_id"])
                #     # try:
                #     #     print("match in service codes csv: ", service_codes[record[1]])
                #     # except:
                #     #     print("no match for service code in csv")
                #     try:
                #         train_uids[msg["train_id"][2:6]] = record[0]
                #         train_uids[msg["train_id"][2:6]] = activations[msg["train_id"]]["train_uid"]
                #         #train_lookup = lookup_by_uid(record[0])
                #         #print("match from lookup by uid origin: ",train_lookup["origin"][0]["description"]+" dest: "+ train_lookup["destination"][0]["description"])
                #     except Exception as e:
                #         print("no match for uid on lookup api", e)


## Showing the data
# for record in records:
#     print(record)
#                 #filehandler = open("train_ids", 'wb') 
#                 #pickle.dump(train_ids, filehandler)

def make_connections():
    print("reset connections")
    logging.critical("resetting connections") 
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

line_count = 0

with open('./train_service_codes/service_codes.csv') as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
        
    for row in csv_reader:
        if line_count == 0:
            line_count += 1
        else:
            service_codes[row[0]] = row[1]
            line_count += 1

_thread.start_new_thread(check_internet, ())

make_connections()

if not dev:
    run_text = RunText()
    if (not run_text.process()):
        run_text.print_help()

while 1:

    now = datetime.datetime.now()

    if now.strftime("%H:%M") == "00:00":
        train_ids = {}
        train_uids = {}
        activations = {}

    if last_mvt_message + 30 < time.perf_counter() or last_td_message + 30 < time.perf_counter():
        logging.critical("attempting connection reset last mvt: "+str(last_mvt_message)+" last td: "+str(last_td_message) + " perf count: "+str(time.perf_counter())) 
        last_mvt_message = time.perf_counter()
        last_td_message = time.perf_counter()
        make_connections()

    if last_mvt_message + 3600 < time.perf_counter() or last_td_message + 3600 < time.perf_counter():
        os.system("sudo reboot")

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
        
    if train_text[0] and train_last_seen[0] + 300 < time.perf_counter():
        train_text[0] = ""
        train_last_seen[0] = 0
        print("north bound train time out")

    if train_text[1] and train_last_seen[1] + 300 < time.perf_counter():
        train_text[1] = ""
        train_last_seen[1] = 0
        print("south bound train time out")

    if train_text[0] == "" and train_text[1] == "":
        show_trains = False

    time.sleep(1)
