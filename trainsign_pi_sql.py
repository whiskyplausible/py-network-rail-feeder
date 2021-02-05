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
import sys
import requests
from requests.auth import HTTPBasicAuth 
import mysql.connector as mysql

dev = True

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
# try:
#     filehandler = open("train_ids", 'rb') 
#     train_ids = pickle.load(filehandler)
# except:
#     print ("couldn't load file")

service_codes = {}
activations = {}

db = mysql.connect(
    host = "localhost",
    user = "nikhil",
    passwd = "Bd75W*0p1hB",
    database = "trains"
)
cursor = db.cursor()


class RunText(): #SampleBase):
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
            if brightness < 251:
                brightness+=4
            time.sleep(0.05)
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

def lookup_by_uid(uid):
    time_now = datetime.datetime.now()
    time_url = time_now.strftime("/%Y/%m/%d")
    url = "http://api.rtt.io/api/v1/json/service/"+str(uid)+time_url
    print("rtt url: ", url)
    try:
        req = requests.get(url, auth = HTTPBasicAuth(creds.RTT_USER, creds.RTT_PASS))
        print("received lookup back from rtt", req.text)
        return req.json()
    except Exception as e: 
        print(e)        
    return None

class TDListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in TDListener "+str(message))
    def on_message(self, headers, messages):
        global train_fake, train_text, train_last_seen, train_change, show_trains, last_td_message
        last_td_message = time.perf_counter()
        try:
            print(".", end='', flush=True)
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
                    logging.critical("Train arrived. "+ str(message))
                    try:
                        service_id = service_codes[train_ids[id]]
                        train_lookup = "no lookup found"

                        for activation in activations:
                            if str(activations[activation]["train_service_code"]) == str(train_ids[id]):
                                act_service_code = str(activations[activation]["train_service_code"])
                                train_uid = activations[activation]["train_uid"]
                                train_lookup = lookup_by_uid(train_uid)

                        with open("uid_lookups.txt", "a") as fh:
                            fh.write("id found: "+id+"\n")
                            fh.write("train service code in activation:" + act_service_code)
                            fh.write("service found: "+service_id+"\n")
                            fh.write("train_ids[id] ", train_ids[id])
                            fh.write("service_code in activations: " + train_uid +"\n")

                            try:
                                fh.write("response: "+train_lookup["origin"][0]["description"]+" "+ train_lookup["destination"][0]["description"]+"\n")
                            except:
                                fh.write("error when writing train_lookup\n")
                        logging.critical("Found service code "+train_ids[id])
                        logging.critical("Found service "+service_id)
                    except:
                        service_id = id # show service code here too if poss?
                        if id in train_ids:
                            logging.critical("Failed to find service, but found this train ID "+train_ids[id])

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
        
        except:
            logging.critical("this is an exception", exc_info=True) 

class MVTListener(stomp.ConnectionListener):

    def on_error(self, headers, message):
        print('received an error "%s"' % message)
        logging.critical("Error in MVTListener "+str(message))
    def on_message(self, headers, messages):
        global last_mvt_message
        last_mvt_message = time.perf_counter()
        #print(G+'received a message "%s"' % message)
        for message in json.loads(messages):
            msg = message['body']
            # if message['header']['msg_type'] == "0001": # this will look up all train activations and find the exact uid and trust id of our train
            #     activations[msg['train_id']] = {
            #         "train_uid": msg['train_uid'],
            #         "train_service_code": msg['train_service_code']
            #     }
            #     #print(sys.getsizeof(activations))
            #     filehandler = open("activations", 'w') 
            #     filehandler.write(json.dumps(activations, indent=4))
            #     filehandler.close()

            stanox_list = [
                msg['reporting_stanox'][0:2] if 'reporting_stanox' in msg else "00",
                msg['next_report_stanox'][0:2] if 'next_report_stanox' in msg else "00",
                msg['loc_stanox'][0:2] if 'loc_stanox' in msg else "00"
            ]
            
            if set(stanox_list).intersection(["68", "75", "81", "76"]) != set():
                logging.critical("found a relevant service "+str(msg))
                train_ids[msg["train_id"][2:6]] = msg["train_service_code"]

                query = "SELECT train_uid, train_service_code FROM activations WHERE train_id = '%s'"
                values = (msg["train_id"],)
                cursor.execute(query, values)
                records = cursor.fetchall()
                for record in records:
                    print("found a match in sql: ", record[0], record[1])
                    try:
                        print("match in service codes csv: ", service_codes[record[1]])
                    except:
                        print("no match for service code in csv")
                    try:
                        train_lookup = lookup_by_uid(record[0])
                        print("match from lookup by uid ",train_lookup["origin"][0]["description"]+" "+ train_lookup["destination"][0]["description"])
                    except:
                        print("no match for uid on lookup api")


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

make_connections()

if not dev:
    run_text = RunText()
    if (not run_text.process()):
        run_text.print_help()

while 1:

    now = datetime.datetime.now()

    if now.strftime("%H:%M") == "00:00":
        train_ids = {}

    if last_mvt_message + 30 < time.perf_counter() or last_td_message + 30 < time.perf_counter():
        logging.critical("attempting connection reset last mvt: "+str(last_mvt_message)+" last td: "+str(last_td_message) + " perf count: "+str(time.perf_counter())) 
        last_mvt_message = time.perf_counter()
        last_td_message = time.perf_counter()
        make_connections()

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