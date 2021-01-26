import stomp
import time

HOSTNAME = "datafeeds.networkrail.co.uk"
USERNAME = ''
PASSWORD = ''
channel = "TD_ALL_SIG_AREA"

class MyListener(stomp.ConnectionListener):
    def on_error(self, headers, message):
        print('received an error "%s"' % message)
    def on_message(self, headers, message):
        print('received a message "%s"' % message)

conn = stomp.Connection(host_and_ports=[(HOSTNAME, 61618)])
conn.set_listener('', MyListener())
conn.start()
conn.connect(username=USERNAME, passcode=PASSWORD)
conn.subscribe(destination=f"/topic/{channel}", id=1, ack='auto')
time.sleep(10)
conn.disconnect()

