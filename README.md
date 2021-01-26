Area seems to be D9 when going south or north, can probably ignore the GL.

So, here:
https://www.opentraintimes.com/maps/signalling/gloucester#T_GLOSTER
Top line is going North, bottom line is going South.

To look up headcode thingy:
https://rail-record.co.uk/train-service-codes/


AC says "So we’ve worked out that going South, when the train moves from signal ref 2019 to 2021 there are around 30 seconds before we see it pass our office.

Likewise going North, when the train moves from signal ref 2020 to 2018  there are around 30 seconds before we see it pass our office."
 
stanox codes we're interested in:
68162
68161
68159
kemble: 75xxx
81xxx yate
lydney/chepstow: 76xxx



OD notes 22/01/2021 - note this requires an older version of stomp, i think I installed the one from July 2019. To get the actual berth data, we need to use the TD service. The one to use is "TRAIN_MVT_ALL_TOC" as although you can subscribe to others they are apparently not necesssarily complete.

The 'headcode' is the 4 alphanumeric digits (called 'descr' on the received data). https://en.wikipedia.org/wiki/Train_reporting_number
This site does a good job at looking them up, so perhaps for now we can just scrape this: https://live.rail-record.co.uk/headcode.php?hc=2O78&date=2021-01-22
The date is required as obviously these codes are specific to the day. Obviously next step would be to look these up ourselves, maybe we can use Darwin or something databases for this.

So all we need to do is look up area_id GL or D9. Look up movement from 2019 to 2021 we have 30 secs before it passes.
Movement from 2020 to 2018 we have 30 seconds.

So to clarify - the TD service gives the fine grained berth-by-berth progress info.

I wonder if we can cross reference from TD to the MVT service. As MVT gives train_service_code and also traid_id both of which I think are unique which the 4 digit head code isn't.
This looks promising - you can lookup the train_service_code here: https://rail-record.co.uk/train-service-codes/

Also found a spreadsheet (in "train_service_code spreadsheet" folder) with all the train service codes on! So basically just need to keep a rolling list of all the unique train_ids reported for all the stanoxs in the gloucester area. Then when there's a TD, it simply cross references it in this table. Probably timestamp them from when they are taken and purge every night or whatever.

# py-network-rail-feeder
Network Data Feeds provide some real-time open data from the rail industry in Great Britain. And this is an Python implementation to collect and download data from UK Network Rail Data Feeds.

## Data Source
This is the site where you register and log in to subscribe different data feeds:
https://datafeeds.networkrail.co.uk/ntrod/myFeeds

There is a wiki page where you could find the documentations about the data feeds:
https://wiki.openraildata.com/index.php/Main_Page

## Install package dependencies
First of all, you need to install all dependencies required by this tool.

```bash
pip install -r requirements.txt
```

## Why use SQL

Since the output of feeds are mostly in JSON format, and it is quite different to constantly saving updated real-time JSON. Therefore, I choose to save it in to sqlite database. And before saving, you need to specify the data schema for creating SQL table. Another reason is there are many fields in the JSON format, and maybe not everything is useful, therefore, you could cherry-pick the fields you need to save.

To define schema, you could check the WIKI page and find the documentation.

## Topics to download and store

There are four topics the readers can choose to download and store from Network Rail data feeds. Namely:

1. __MVT__ - Train movement
2. __PPM__ - Public performance measure
3. __VSTP__ - Very short term planning
4. __TD__ - Train describer

__Before running the script, readers must register and subscribe the corresponding feeds.__ 

Moreover, there is also a topic called 'SCHEDULE' that can be downloaded in a similar way to VSTP, however, it requires extra authorisation to access to the files. If interested, readers can gain the access and follow the similar step to complete the download.

## How to use it?

An example is given in the `example.py` and Train Movement is chosen as the topic I want to download.

For instance:

```python
from topicmapping import TopicMapping
from datafeeder import RailDataFeeder

# four topics to choose from - 1. MVT 2. PPM 3. VSTP 4. TD
TOPIC = "MVT"

train_rdf = RailDataFeeder(
                    db_name=TopicMapping[TOPIC][2], 
                    channel=TopicMapping[TOPIC][1], 
                    topic=TOPIC,
                    schema=TopicMapping[TOPIC][0],
                    username=USERNAME,
                    password=PASSWORD,
                    drop_if_exists=True,
                    view=False
)

train_rdf.download_feed()
```
__The users simply needs to state the topic they want to choose and the script will automatically connect to the data feeds and download the required files.__

The mandatory keywords are explained as follows:

- `db_name`: The name of the database you would like to save the SQL
- `channel`: The name of the channel from which to download data. Keep in mind that you need to register for the channel before downloading.
- `topic`: The topic of the channel. Valid topic is now `MVT` only.
- `schema`: The data schema. THose can be found in wiki, and maybe you are not into all columns/features, so just define the columns of features you want to download.
- `username/password`: If you save them as environment variable with `DATAFEED_USERNAME` and `DATAFEED_PW`, then they will be automatically uploaded. Otherwise, you have to define it in initialization.

This tool also provides a function that allows you to convert the downloaded SQL table into pandas Dataframe. You can achieve this by doing:
```
import pandas as pd
train_rdf.to_pandas()
```
