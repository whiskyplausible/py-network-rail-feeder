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
retry_time = 30

train_fake = [False, False, False, False]

train_ids = {}
train_ids_ts = {}
train_uids = {}
train_uids_ts = {}
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
    except:
        print ("couldn't load file: activations")

    try:
        filehandler = open("train_ids", 'rb') 
        train_ids = pickle.load(filehandler)
        filehandler.close()
    except:
        print ("couldn't load file: train_ids")

    try:
        filehandler = open("train_uids", 'rb') 
        train_uids = pickle.load(filehandler)
        filehandler.close()
    except:
        print ("couldn't load file: train_uids")

def internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
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

            for box in range(0,24):
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
    try:
        req = requests.get(url, auth = HTTPBasicAuth(creds.RTT_USER, creds.RTT_PASS))
        api_led = False
        if req.status_code != 200:
            api_led = True
        return req.json()

    except Exception as e: 
        print(e)        
        api_led = True

    return None

def get_dt():
    now = datetime.datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    return dt_string

def get_dt_file():
    now = datetime.datetime.now()
    dt_string = now.strftime("%d-%m-%Y-%H-%M-%S")
    return dt_string


def log_everything():
    filehandler = open("activations_"+get_dt_file(), 'w') 
    filehandler.write(json.dumps(activations, indent=4))
    filehandler.close()
    filehandler = open("train_uids_"+get_dt_file(), 'w') 
    filehandler.write(json.dumps(train_uids, indent=4))
    filehandler.close()
    filehandler = open("train_ids_"+get_dt_file(), 'w') 
    filehandler.write(json.dumps(train_ids, indent=4))
    filehandler.close()

class TDListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in TDListener "+str(message))
    def on_message(self, headers, messages):
        global train_fake, train_text, train_last_seen, train_change, show_trains, last_td_message, td_led
        td_led = not td_led
        last_td_message = time.perf_counter()
        try:
            for message in json.loads(messages):

                if "CA_MSG" in message and message["CA_MSG"]["area_id"] in ["D9"] and message["CA_MSG"]["to"] in [ "2021", "2018"]: #2021 south 2018 north
                    show_trains = True
                    
                    id = message["CA_MSG"]["descr"]
                    service_id = id                    
                    logging.critical("Train arrived at monitored berths. "+ str(message))

                    if id in train_ids and train_ids[id] in service_codes:
                        service_id = service_codes[train_ids[id]]
                        print(get_dt(), "service code found in csv ", id, service_id)
                    else:
                        print(get_dt(), "Couldn't find id in csv service codes: ", id)

                    possible_uid = None
                    is_in_uids = id in train_uids
                    for activation in activations:
                        if activation[2:6] == id and not is_in_uids and service_id == id:
                            possible_uid = activations[activation]["train_uid"]

                    if is_in_uids or possible_uid:
                        print(get_dt(), "Found id in train_uids, trying api lookup")
                        train_lookup = None
                        try:
                            if possible_uid:
                                train_lookup = lookup_by_uid(possible_uid)
                                print("Couldn't find this train in uids, so making a guess it might be this one by checking activations.")
                            else:
                                train_lookup = lookup_by_uid(train_uids[id])

                            print(get_dt(), "match from lookup by uid origin: ",train_lookup["origin"][0]["description"]+" dest: "+ train_lookup["destination"][0]["description"])
                            atocName = "" if train_lookup["atocName"] == "Unknown" else train_lookup["atocName"]
                            if possible_uid:
                                atocName = "[Guessing] " + atocName
                            service_id = atocName + " [" + train_lookup['powerType'] + "] "
                            service_id += train_lookup["origin"][0]["description"]+" to "+ train_lookup["destination"][0]["description"]
 
                        except Exception:
                            print(get_dt(), "train lookup failed: ", traceback.format_exc())
                            print(get_dt(), "logging everthing")
                            log_everything()
                    else:
                        print(get_dt(), "train id ", id, "not found in train_uids")
                        log_everything()

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
                    print("************************************************************")

                if "CA_MSG" in message and message["CA_MSG"]["area_id"] in ["D9"] and message["CA_MSG"]["to"] in [ "2023", "2016"]: #train has passed by now
                    if message["CA_MSG"]["to"] == "2023":
                        train_text[1] = ""
                        train_last_seen[1] = 0
                        #print(get_dt(), "train has passed south")
                    else:
                        train_text[0] = ""
                        train_last_seen[0] = 0
                        #print(get_dt(), "train has passed north")

                    if train_text[0] == "" and train_text[1] == "":
                        show_trains = False

                    train_change = True
        
        except:
            logging.critical("this is an exception", exc_info=True) 
            print(get_dt(), "error in td loop: ", traceback.format_exc())

class MVTListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in MVTListener "+str(message))
    def on_message(self, headers, messages):
        global last_mvt_message, activations, train_ids, train_uids, train_ids_ts, train_uids_ts, activations, mvt_led
        mvt_led = not mvt_led
        last_mvt_message = time.perf_counter()
        for message in json.loads(messages):
            msg = message['body']

            if message['header']['msg_type'] == "0001": # this will look up all train activations and find the exact uid and trust id of our train
                activations[msg['train_id']] = {
                    "train_uid": msg['train_uid'],
                    "train_service_code": msg['train_service_code'],
                    "timestamp": datetime.datetime.now()
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
                train_ids[msg["train_id"][2:6]] = msg["train_service_code"]
                train_ids_ts[msg["train_id"][2:6]] = datetime.datetime.now()
                if useDisk:
                    filehandler = open("train_ids", 'wb') 
                    pickle.dump(train_ids, filehandler)
                    filehandler.close()

                if msg["train_id"] in activations:
                    train_uids[msg["train_id"][2:6]] = activations[msg["train_id"]]["train_uid"]
                    train_uids_ts[msg["train_id"][2:6]] = datetime.datetime.now()

                    if useDisk:
                        filehandler = open("train_uids", 'wb') 
                        pickle.dump(train_uids, filehandler)
                        filehandler.close()
                else:
                    pass

def make_connections():
    print(get_dt(), "reset connections")
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

def checking_thread():
    global train_ids, train_uids, train_ids_ts, train_uids_ts, activations, last_mvt_message, last_td_message, retry_time
    global show_trains, current_display, train_change, train_text, train_last_seen
    print("starting checking thread")
    while 1:

        now = datetime.datetime.now()

        if now.strftime("%H:%M") == "00:00":
            for activation in activations:
                delta = now - activations[activation]["timestamp"]
                if delta.days > 2:
                    activations.pop(activation, None)

            for train_id in train_ids_ts:
                delta = now - train_ids_ts[train_id]
                if delta.days > 2:
                    train_ids.pop(train_id, None)
                    train_ids_ts.pop(train_id, None)

            for train_uid in train_uids_ts:
                delta = now - train_uids_ts[train_uid]
                if delta.days > 2:
                    train_uids.pop(train_uid, None)
                    train_uids_ts.pop(train_uid, None)

            print(get_dt(), "wiping variables as is midnight")

        if last_mvt_message + retry_time < time.perf_counter() or last_td_message + retry_time < time.perf_counter():
            logging.critical("attempting connection reset last mvt: "+str(last_mvt_message)+" last td: "+str(last_td_message) + " perf count: "+str(time.perf_counter())) 
            print("no messages received for 30 seconds..... ")
            retry_time += 30
            make_connections()

        if last_mvt_message + 3600 < time.perf_counter() or last_td_message + 3600 < time.perf_counter():
            os.system("sudo reboot")

        if show_trains and current_display != "TRAINS":
            current_display = "TRAINS"
            #print(get_dt(), "showing trains", train_text)

        if not show_trains and current_display == "TRAINS":
            current_display = "BLANK"
            #print(get_dt(), "display off")

        if train_change and show_trains:
            train_change = False
            #print(get_dt(), "train approaching")
            print(train_text)

        if train_change and not show_trains:
            train_change = False   
            #print(get_dt(), "train has now passed by")
            
        if train_text[0] and train_last_seen[0] + 300 < time.perf_counter():
            train_text[0] = ""
            train_last_seen[0] = 0
            print(get_dt(), "north bound train time out")

        if train_text[1] and train_last_seen[1] + 300 < time.perf_counter():
            train_text[1] = ""
            train_last_seen[1] = 0
            print(get_dt(), "south bound train time out")

        if train_text[0] == "" and train_text[1] == "":
            show_trains = False

        time.sleep(1)

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
_thread.start_new_thread(checking_thread, ())

make_connections()

if not dev:
    run_text = RunText()
    if (not run_text.process()):
        run_text.print_help()

while 1:
    time.sleep(10)