## TODO
## Wrap all the make_connection in a try loop as at the moment it's crashing the checking thread!!!!
## In the checking thread wrap anything that could crash in a try: block as we don't want this to crash.
## Add secondary watch dog that checks if the checking loop has crashed and restarts then?
## some external logging?!

import pickle
import stomp
import json
import time
import creds
import csv 
import logging
import datetime
import ntplib
from pytz import timezone
import os
import socket
import requests
import traceback
import _thread
import sys
from requests.auth import HTTPBasicAuth 
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
import logging

sentry_logging = LoggingIntegration(
    level=logging.INFO,        # Capture info and above as breadcrumbs
    event_level=logging.CRITICAL  # Send errors as events
)

sentry_sdk.init(
    "https://05d110c58eb94bc487cf067ed4f2254a@o536441.ingest.sentry.io/5655032",
    traces_sample_rate=1.0,
    integrations=[sentry_logging]
)

dev = False
useDisk = True
logDisk = False

if not dev:
    from samplebase import SampleBase
    from rgbmatrix import graphics

if logDisk:
    logging.basicConfig(
        filename='trains.log', filemode='a',
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.CRITICAL,
        datefmt='%Y-%m-%d %H:%M:%S')
else:
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.CRITICAL,
        datefmt='%Y-%m-%d %H:%M:%S')

HOSTNAME = "datafeeds.networkrail.co.uk"
USERNAME = creds.USERNAME
PASSWORD = creds.PASSWORD
td_channel = "TD_ALL_SIG_AREA"
mvt_channel = "TRAIN_MVT_ALL_TOC"

a_lock = _thread.allocate_lock()

start_time = time.perf_counter()
show_trains = False
train_last_seen = [0,0]
train_text = ["", ""]
train_change = False
current_display = "BLANK"
last_td_message = start_time
last_mvt_message = start_time
last_screen_update = start_time
last_check_thread_run = start_time
last_screen = start_time
mvt_retry_time = 1800
td_retry_time = 1800
purged = False
td_conn = None
mvt_conn = None

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
        print("trying to read train data...")
        filehandler = open("/mnt/mydisk/train_data", "rb")
        all_data = pickle.load(filehandler)
        filehandler.close()
        train_ids = all_data["train_ids"]
        train_ids_ts = all_data["train_ids_ts"]
        activations = all_data["activations"]
        train_uids = all_data["train_uids"]
        train_uids_ts = all_data["train_uids_ts"]
        print("read train data OK i think...")
    except:
        print("Failed to load train_data file off USB")

    # try:
    #     filehandler = open("activations", 'rb') 
    #     activations = pickle.load(filehandler)
    #     filehandler.close()
    # except:
    #     print ("couldn't load file: activations")

    # try:
    #     filehandler = open("train_ids", 'rb') 
    #     train_ids = pickle.load(filehandler)
    #     filehandler.close()
    # except:
    #     print ("couldn't load file: train_ids")

    # try:
    #     filehandler = open("train_uids", 'rb') 
    #     train_uids = pickle.load(filehandler)
    #     filehandler.close()
    # except:
    #     print ("couldn't load file: train_uids")

def internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

def set_time():
    try:
        ntp_time = ntplib.NTPClient()
        response = ntp_time.request('uk.pool.ntp.org', version=3)
        response.offset
        now = datetime.datetime.fromtimestamp(response.tx_time, timezone('Europe/London'))
        nowstr = now.strftime("%d %b %Y %H:%M:%S")
        print("got time from ntp, trying to set in linux")
        os.system('sudo date -s "'+nowstr+'"')
        print("finished setting time in linux")
    except:
        print("failed to get/set time")
        
class RunText(SampleBase): #SampleBase):
    def __init__(self, *args, **kwargs):
        print("init")
        super(RunText, self).__init__(*args, **kwargs)
        self.parser.add_argument("-t", "--text", help="The text to scroll on the RGB LED panel", default="Hello world!")

    def run(self):
        global last_screen_update

        print("starting")
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        font = graphics.Font()
        font.LoadFont("../../../fonts/7x13.bdf")
        timeFont = graphics.Font()
        timeFont.LoadFont("../../../fonts/6x10.bdf")
        posN = offscreen_canvas.width
        posS = offscreen_canvas.width
        approach = [0,0]
        brightness = 0
        screen_train_text = ["",""]
        redColor = graphics.Color(255,0,0)

        while True:
            last_screen_update = time.perf_counter()
            dirColor = graphics.Color(0,0,brightness)
            textColor = graphics.Color(brightness, brightness, 0)

            now = datetime.datetime.now()
            timeNow = now.strftime('%H:%M:%S')
            offscreen_canvas.Clear()
            
            try:
                if train_text[0] and not screen_train_text[0]:
                    approach[0] = time.perf_counter()
                    flash = time.perf_counter()
                if train_text[1] and not screen_train_text[1]:
                    approach[1] = time.perf_counter()
                    flash = time.perf_counter()
            except:
                print("thread nonsense")

            try:
                screen_train_text = train_text.copy()
            except:
                print("Threading problem?")
                screen_train_text = ["",""]

            if approach[0] > 0:
                if approach[0] + 3 < time.perf_counter():
                    approach[0] = 0
                else:
                   graphics.DrawText(offscreen_canvas, font, 35, 10, graphics.Color(255,150,0), "TRAIN APPROACHING")
            else:
                lenN = graphics.DrawText(offscreen_canvas, font, posN, 10, textColor, screen_train_text[0])
                posN -= 1
                if (posN + lenN < 35):
                    posN = offscreen_canvas.width

            if approach[1] > 0:
                if approach[1] + 3 < time.perf_counter():
                    approach[1] = 0
                else:
                   graphics.DrawText(offscreen_canvas, font, 35, 21, graphics.Color(255,150,0), "TRAIN APPROACHING")
            else:
                lenS = graphics.DrawText(offscreen_canvas, font, posS, 21, textColor, screen_train_text[1])
                posS -= 1
                if (posS + lenS < 35):
                    posS = offscreen_canvas.width

            # lenN = graphics.DrawText(offscreen_canvas, font, posN, 10, textColor, screen_train_text[0])
            # posN -= 1
            # if (posN + lenN < 35):
            #     posN = offscreen_canvas.width
            # lenS = graphics.DrawText(offscreen_canvas, font, posS, 21, textColor, screen_train_text[1])
            # posS -= 1
            # if (posS + lenS < 35):
            #     posS = offscreen_canvas.width

            for box in range(0,24):
                graphics.DrawLine(offscreen_canvas,0,box, 35,box,graphics.Color(0,0,0))

            graphics.DrawText(offscreen_canvas, font, 0, 10, dirColor, "NORTH")
            graphics.DrawText(offscreen_canvas, font, 0, 21, dirColor, "SOUTH")
            graphics.DrawText(offscreen_canvas, timeFont, 72, 30, redColor, timeNow)
            
            try:
                if td_led:
                    graphics.DrawLine(offscreen_canvas,0,0,0,0,graphics.Color(50,0,0))

                if mvt_led:
                    graphics.DrawLine(offscreen_canvas,1,0,1,0,graphics.Color(0,0,50))

                if api_led:
                    graphics.DrawLine(offscreen_canvas,2,0,2,0,graphics.Color(0,50,0))
            except:
                print("thread problem with leds?")

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
    return None
    #a_lock.acquire()
    #print("acq: log_everything")
    if not useDisk:
        return None
    filehandler = open("activations_"+get_dt_file(), 'w') 
    filehandler.write(json.dumps(activations, indent=4, default=str))
    filehandler.close()
    filehandler = open("train_uids_"+get_dt_file(), 'w') 
    filehandler.write(json.dumps(train_uids, indent=4))
    filehandler.close()
    filehandler = open("train_ids_"+get_dt_file(), 'w') 
    filehandler.write(json.dumps(train_ids, indent=4))
    filehandler.close()
    #a_lock.release()
    #print("rel: log_everything")

class TDListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        #logging.critical("Error in TDListener "+str(message))
        
    def on_message(self, headers, messages):
        global train_fake, train_text, train_last_seen, train_change, show_trains, last_td_message, td_led
        td_led = not td_led
        a_lock.acquire()
        #print("acq: td")

        last_td_message = time.perf_counter()
       
        try:
            for message in json.loads(messages):
                # if time.perf_counter() - start_time > 5 and not train_fake[0]:
                #     train_fake[0] = True
                #     print("faking a train!")
                #     message = {
                #         "CA_MSG": {
                #             "area_id": "D9",
                #             "to": "2018",
                #             "descr": "0101"
                #         }
                #     }

                # if time.perf_counter() - start_time > 10 and not train_fake[2]:
                #     train_fake[2] = True
                #     print("faking a train!")
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
                    #logging.critical("Train arrived at monitored berths. "+ str(message))

                    if id in train_ids and train_ids[id] in service_codes:
                        service_id = "[Guess] " + service_codes[train_ids[id]]
                        print(get_dt(), "service code found in csv ", id, service_id)
                    else:
                        print(get_dt(), "Couldn't find id in csv service codes: ", id)

                    possible_uid = None
                    is_in_uids = id in train_uids
                    act_copy = activations.copy()

                    for activation in act_copy:
                        if activation[2:6] == id and not is_in_uids and service_id == id:
                            possible_uid = activations[activation]["train_uid"]

                    if is_in_uids or possible_uid:
                        print(get_dt(), "Found id in train_uids, trying api lookup")
                        train_lookup = None
                        a_lock.release()
                        #print("rel: td middle")

                        try:
                            if possible_uid:
                                train_lookup = lookup_by_uid(possible_uid)
                                print("Couldn't find this train in uids, so making a guess it might be this one by checking activations.")
                            else:
                                train_lookup = lookup_by_uid(train_uids[id])

                            print(get_dt(), "match from lookup by uid origin: ",train_lookup["origin"][0]["description"]+" dest: "+ train_lookup["destination"][0]["description"])
                            atocName = "" if train_lookup["atocName"] == "Unknown" else train_lookup["atocName"]
                            if possible_uid:
                                atocName = "[Guess] " + atocName
                            service_id = atocName + " [" + train_lookup['powerType'] + "] "
                            service_id += train_lookup["origin"][0]["description"]+" to "+ train_lookup["destination"][0]["description"]

                            if train_lookup["origin"][0]["tiploc"] == "BRKELEY" or train_lookup["origin"][0]["tiploc"] == "BRDGWUY":
                                service_id = "!!!NUCLEAR!!!NUCLEAR!!! " + service_id

                        except Exception:
                            print(get_dt(), "train lookup failed: ", traceback.format_exc())
                            if 'train_lookup' in locals():
                                print("response from lookup: ", train_lookup)
                            print(get_dt(), "logging everthing")
                            a_lock.acquire()
                            log_everything()
                            a_lock.release()

                        a_lock.acquire()
                        #print("acq: td middle")

                    else:
                        print(get_dt(), "train id ", id, "not found in train_uids")
                        print(get_dt(), "train_uids size ", sys.getsizeof(train_uids))

                        log_everything()

                    #print("rel: td last")
                    a_lock.release()
                    
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
                    a_lock.acquire()
                    #print("acq: td last")

                    if message["CA_MSG"]["to"] == "2021":
                        train_text[1] = service_id
                        train_last_seen[1] = time.perf_counter() 
                    else:
                        train_text[0] = service_id
                        train_last_seen[0] = time.perf_counter() 

                    train_change = True
                    logging.critical(service_id)
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
            #logging.critical("this is an exception", exc_info=True) 
            print(get_dt(), "error in td loop: ", traceback.format_exc())
        a_lock.release()        
        #print("rel: td finish")

class MVTListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        #logging.critical("Error in MVTListener "+str(message))
    def on_message(self, headers, messages):
        global last_mvt_message, activations, train_ids, train_uids, train_ids_ts, train_uids_ts, mvt_led
        mvt_led = not mvt_led
        a_lock.acquire()
        #print("acq: mvt")

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

            stanox_list = [
                msg['reporting_stanox'][0:2] if 'reporting_stanox' in msg else "00",
                msg['next_report_stanox'][0:2] if 'next_report_stanox' in msg else "00",
                msg['loc_stanox'][0:2] if 'loc_stanox' in msg else "00"
            ]
            
            if set(stanox_list).intersection(["68", "75", "81", "76"]) != set():
                train_ids[msg["train_id"][2:6]] = msg["train_service_code"]
                train_ids_ts[msg["train_id"][2:6]] = datetime.datetime.now()

                if msg["train_id"] in activations:
                    train_uids[msg["train_id"][2:6]] = activations[msg["train_id"]]["train_uid"]
                    train_uids_ts[msg["train_id"][2:6]] = datetime.datetime.now()

                else:
                    pass
        a_lock.release()
        #print("rel: mvt")

def make_connections():
    global td_conn, mvt_conn
    print(get_dt(), "reset connections")
    logging.critical("resetting connections") 
    # Need to wrap these in a try loop. As this will crash the checking_thread otherwise!!!

    try:
        mvt_conn.disconnect()
    except:
        print("no connections to disconnect mvt_conn")

    try:
        td_conn.disconnect()
    except:
        print("no connections to disconnect td_conn")

    try:
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
    except:
        print("failed to reset connections")

def check_checking_thread():
    global last_check_thread_run, useDisk
    while True:
        if last_check_thread_run + 3600 < time.perf_counter():
            print(get_dt(),"trying to reboot in the check_checking_thread")
            logging.critical("trying reboot as main_checking_thread seems to be dead")
            time.sleep(30)
            os.system("sudo reboot")

        time.sleep(600)

def checking_thread():
    global train_ids, train_uids, train_ids_ts, train_uids_ts, activations, last_mvt_message, last_td_message, mvt_retry_time, td_retry_time
    global show_trains, current_display, train_change, train_text, train_last_seen, purged, last_screen, last_screen_update, last_check_thread_run
    print("starting checking thread")
    logging.critical("starting checking thread.")
    usb_dump_done = False
    while 1:

        now = datetime.datetime.now()
        last_check_thread_run = time.perf_counter()
        try:
            last_screen = last_screen_update
        except:
            last_screen = time.perf_counter()

        if now.strftime("%H:%M") == "00:01":
            purged = False

        if now.strftime("%M")[1] == "0" and not usb_dump_done and useDisk:
            usb_dump_done = True
            print("trying to save data on usb, the 10 minute thing")
            a_lock.acquire()
            print("got lock, saving...")
            try:
                filehandler = open("/mnt/mydisk/train_data", "wb")
                save_obj = {
                    "train_ids": train_ids,
                    "train_ids_ts": train_ids_ts,
                    "train_uids": train_uids,
                    "train_uids_ts": train_uids_ts,
                    "activations": activations
                }
                pickle.dump(save_obj, filehandler)
                save_obj = None
                filehandler.close()
                print("saved pickle data.")
            except:
                print(get_dt(), "Failed to write train log stuff.")

            a_lock.release()
            print("lock released")

        if now.strftime("%M")[1] == "1":
            usb_dump_done = False

        if now.strftime("%H:%M") == "00:00" and not purged:
            mvt_retry_time = 1800
            td_retry_time = 1800

            purged = True
            a_lock.acquire()
            #print("acq: ct")

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

            a_lock.release()
            #print("rel: ct")
            set_time()
            print(get_dt(), "wiped variables as is midnight")

        a_lock.acquire()
        #print("acq: ct 2")

        start = datetime.time(6)
        end = datetime.time(23, 59)

        if start <= now.time() <= end:
            if last_mvt_message + mvt_retry_time < time.perf_counter():
                #logging.critical("attempting mvt connection reset last mvt: "+str(last_mvt_message)+" last td: "+str(last_td_message) + " perf count: "+str(time.perf_counter())) 
                print(get_dt(),"no mvt messages received for a while..... ")
                mvt_retry_time += 1800
                make_connections()

            if last_td_message + td_retry_time < time.perf_counter():
                #logging.critical("attempting td connection reset last mvt: "+str(last_mvt_message)+" last td: "+str(last_td_message) + " perf count: "+str(time.perf_counter())) 
                print(get_dt(),"no td messages received for a while..... ")
                td_retry_time += 1800
                make_connections()

            if last_mvt_message + 4000 < time.perf_counter() or last_td_message + 4000 < time.perf_counter():
                print(get_dt(),"trying to reboot in the 4000 wait bit")
                logging.critical("rebooting after 4000 second wait thing")
                time.sleep(30)
                os.system("sudo reboot")

        if last_screen + 300 < time.perf_counter():
            print(get_dt(),"trying to reboot as screen hasn't updated itself in last 10 mins")
            logging.critical("rebooting as screen thread not responding")
            time.sleep(30)
            os.system("sudo reboot")

        a_lock.release()
        #print("rel: ct 2")

        if show_trains and current_display != "TRAINS":
            current_display = "TRAINS"
            #print(get_dt(), "showing trains", train_text)

        if not show_trains and current_display == "TRAINS":
            current_display = "BLANK"
            #print(get_dt(), "display off")

        if train_change and show_trains:
            train_change = False
            #print(get_dt(), "train approaching")
            #print(train_text)

        if train_change and not show_trains:
            train_change = False   
            #print(get_dt(), "train has now passed by")

        a_lock.acquire()
        #print("acq: ct 3")

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

        a_lock.release()
        #print("rel: ct 3")

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
_thread.start_new_thread(check_checking_thread, ())

make_connections()
set_time()
logging.critical("starting up")
if not dev:
    run_text = RunText()
    if (not run_text.process()):
        run_text.print_help()

while 1:
    time.sleep(10)