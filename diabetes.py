import os, sys
import pathlib
from collections import defaultdict
import datetime

sys.path.append(os.path.abspath('/home/kevin/vayrac/git/tidepool/data-science-tidepool-api-python'))
from data_science_tidepool_api_python.makedata.tidepool_api import TidepoolAPI

import json
import csv

import common

"""
     66 basal
     47 wizard
     47 bolus
     38 smbg
     28 pumpSettings.basalSchedules
     16 pumpSettings.carbRatio
      9 deviceEvent
      4 pumpSettings.insulinSensitivity
      4 pumpSettings.bgTarget
      1 upload
"""

class TimeRange():
    def __init__(self, ev_type, value, unit, start_time):
        self.ev_type = ev_type
        self.value = value
        self.unit = unit
        self.start_time = start_time

    def __str__(self):
        return f"{self.ts} | {self.ev_type}[{self.value}{self.unit}|>{self.start_time}]"

    def __repr__(self):
        return str(self)

class Event():
    def __init__(self, ev_type, value, unit):
        self.ev_type = ev_type
        self.value = value
        self.unit = unit
        self.ts = None

    def __str__(self):
        return f"{self.ts} | {self.ev_type}[{self.value}{self.unit}]"

    def __repr__(self):
        return str(self)

def CGMEvent(value, unit):
    return Event("cgm", value, unit)

def ScanEvent(value, unit):
    return Event("scan", value, unit)

def StripEvent(value, unit):
    return Event("strip", value, unit)

def AcetoneEvent(value, unit):
    return Event("acetone", value * 1000, unit)

def GlycemiaEvent(value, units):
    return Event("glycemia", value, units)

def CarbRatioEvent(value, units):
    return Event("carbsRatio", value, units)

class Entry():
    def __init__(self):
        self.events = []
        self.ts = None

    def add_event(self, ts, event):
        self.events.append(event)
        event.ts = ts

    def __str__(self):
        return "["+", ".join(map(str, self.events)) + "]"

    def __repr__(self):
        return str(self)

entries = defaultdict(Entry)

def CarbsEvent(value):
    return Event("carbs", value, "g")

def BolusEvent(value):
    return Event("bolus", value, "u")

def NewReservoirEvent():
    return Event("newReservoir", 1, "")

def NewCatheEvent():
    return Event("newCathe", 1, "")

def CarbsRatioTimeRange(value, start_time):
    return TimeRange("carbsRatioRange", value, "g/u", start_time)

def BasalTimeRange(value, start_time):
    return TimeRange("basalRange", value, "u/h", start_time)

def parse_tidepool(cache_file):
    REFRESH = False
    if REFRESH:
        username = "..."
        password = "..."
        tp_api = TidepoolAPI(username, password)
        print("Logging into Tidepool ...")
        tp_api.login()

        startdate = datetime.datetime(2021, 7, 8)
        enddate = datetime.datetime.now()
        print("Querying Tidepool ...")
        user_data = tp_api.get_user_event_data(startdate, enddate)
        print("Saving into cache file ...")
        with open(cache_file, 'w') as cache_f:
            json.dump(user_data, cache_f)

    with open(cache_file) as cache_f:
        user_data = json.load(cache_f)

    TS_DEVICE_PATTERN = '%Y-%m-%dT%H:%M:%S'
    TS_PATTERN = '%Y-%m-%dT%H:%M:%S.000Z'
    TS_TIME_PATTERN = '%Y-%m-%dT%H:%M:%S+02:00' # 2021-10-03T10:52:28+02:00
    # http://developer.tidepool.org/data-model/device-data/types/basal/

    for row in user_data:
        if row["type"] == "upload":
            continue
            ts = datetime.datetime.strptime(local_time, TS_TIME_PATTERN) # eg: 2021-09-05T08:45:59.000Z
        local_time = row["deviceTime"]

        ts = datetime.datetime.strptime(local_time, TS_DEVICE_PATTERN) # eg: '2021-10-03T08:50:39.000Z'

        if row["type"] == "wizard":
# {'bgInput': 77.9999381522,
#  'bgTarget.high': 140.00005066949998,
#  'bgTarget.low': 100.00003619249999,
#  'bolus': '518c9413bb7a26daadde27d54e710efd',
#  'carbInput': 37,
#  'insulinCarbRatio': 28,
#  'insulinOnBoard': 0,
#  'insulinSensitivity': 200.00007238499998,
#  'localTime': '2021-09-05T08:45:59.000Z',
#  'recommended.carb': 1.3,
#  'recommended.correction': 6.5328,
#  'recommended.net': 1.1,
#  'units': 'mg/dL',
            if row["carbInput"]:
                entries[ts].add_event(ts, CarbsEvent(row["carbInput"]))
            if "bgInput" in row:
                entries[ts].add_event(ts, GlycemiaEvent(row["bgInput"], row["units"]))
            if "insulinCarbRatio" in row:
                entries[ts].add_event(ts, CarbRatioEvent(row["insulinCarbRatio"], "g/u"))
            pass
        elif row["type"] == "basal":
# {'deliveryType': 'scheduled',
#  'duration': 240,
#  'localTime': '2021-09-05T08:00:00.000Z',
#  'rate': 0.05,
#  'scheduleName': 'Pattern 1',
            pass
        elif row["type"] == "bolus":
# {'localTime': '2021-09-05T08:46:00.000Z',
#  'normal': 1.1,
#  'subType': 'normal',
            if row["subType"] == "normal":
                entries[ts].add_event(ts, BolusEvent(row["normal"]))
                pass
            elif row["subType"] == "dual/square":
                # {'_deduplicator': {'hash': 'RfyTx5FL2w83YaiAfNotpNo8Z4kGBIjCiJ1p0EEm4Lk='}, 'clockDriftOffset': 0, 'conversionOffset': 0, 'deviceId': 'MMT-1712:NG2629137H', 'deviceTime': '2021-10-16T19:06:58', 'duration': 1740000, 'expectedDuration': 1800000, 'expectedExtended': 0.3, 'extended': 0.3, 'id': '7042a4c2a89e1f5f25e0460b044ee749', 'normal': 0.2, 'payload': {'logIndices': [2155727818]}, 'revision': 1, 'subType': 'dual/square', 'time': '2021-10-16T17:06:58.000Z', 'timezoneOffset': 120, 'type': 'bolus', 'uploadId': '770530ce3b3d97fc4f0ebb0d0bdd2a2f'}
                pass
            else:
                import pdb;pdb.set_trace()

            pass
        elif row["type"] == "smbg":
            # Self-Monitored Blood Glucose
# {'localTime': '2021-09-05T08:45:59.000Z',
#  'subType': 'manual',
#  'units': 'mg/dL',
#  'value': 77.9999381522}
            if row["subType"] == "manual":
                # coverted by wizard
                pass
            elif row["subType"] == "linked":
                # ignore
                pass
            else:
                #import pdb;pdb.set_trace()
                pass
            pass
        elif row["type"] == "pumpSettings":
            # row["carbRatio"]
            for ratio in row["carbRatio"]:
                start_time = datetime.timedelta(milliseconds=ratio["start"])
                entries[ts].add_event(ts, CarbsRatioTimeRange(ratio["amount"], start_time))
            del row["carbRatio"]

            # row["basalSchedules"]
            for basal_pattern, basal_sched in row["basalSchedules"].items():
                for basal in basal_sched:
                    start_time = datetime.timedelta(milliseconds=basal["start"])
                    entries[ts].add_event(ts, BasalTimeRange(basal["rate"], start_time))
            del row["basalSchedules"]

            # row["activeSchedule"]
            # Pattern 1

            # row["basal"]
            # {'rateMaximum': {'units': 'Units/hour', 'value': 2}}

            # row["bolus"]
            # {'amountMaximum': {'units': 'Units', 'value': 10}, 'calculator': {'enabled': True, 'insulin': {'duration': 120, 'units': 'minutes'}}, 'extended': {'enabled': False}}

            # insulinSensitivity
            # [{'amount': 11.1015, 'start': 0}]

            # bgTarget
            # [{'high': 7.77105, 'low': 5.55075, 'start': 0}]

        elif row["type"] == "deviceEvent":
# {'localTime': '2021-09-07T13:05:22.000Z',
#  'subType': 'reservoirChange',
            if row["subType"] == "reservoirChange":
                entries[ts].add_event(ts, NewReservoirEvent())
            elif row["subType"] == "prime":
                if row["primeTarget"] == 'cannula':
                    entries[ts].add_event(ts, NewCatheEvent())
                elif row["primeTarget"] == 'tubing':
                    # ignore
                    pass
                else:
                    import pdb;pdb.set_trace()
                    pass
            elif row["subType"] == "status":
                if row["status"] == "suspended":
                    # future work
                    # {"logIndices":[2152442090],"resumed":{"cause":"User resumed"},"suspended":{"cause":"User suspend"}}
                    # {"logIndices":[2152336490],"resumed":{"cause":"User resumed"},"suspended":{"cause":"Set change suspend"}}
                    pass
                else:
                    import pdb;pdb.set_trace()
                pass
            else:
                import pdb;pdb.set_trace()
            pass
        elif row["type"] == "upload":
# {'computerTime': '2021-09-13T10:30:45',
#  'deviceManufacturers': '["Medtronic"]',
#  'deviceModel': '1712',
#  'deviceSerialNumber': 'NG2629137H',
#  'deviceTags': '["cgm","insulin-pump"]',
#  'deviceTime': '2021-09-13T10:29:07',
#  'localTime': '2021-09-13T10:30:45.000Z',
#  'time': '2021-09-13T10:30:45+02:00',
#  'timeProcessing': 'across-the-board-timezone',
#  'timezone': 'Europe/Paris',
#  'timezoneOffset': 120,
#  'uploadId': '83a2277e1e7ef26e37944e5156b9e144',
#  'version': '2.37.1'}
            pass
        else:
            print(row)


def parse_libreview(filename):
    return False
    RECORD_TYPE_HISTORIC = "0"
    RECORD_TYPE_SCAN = "1"
    RECORD_TYPE_STRIP = "2"
    RECORD_TYPE_ACETONE = "3"

    RECORD_TYPES = {
        RECORD_TYPE_HISTORIC: "Historic Glucose mg/dL",
        RECORD_TYPE_SCAN:     "Scan Glucose mg/dL",
        RECORD_TYPE_STRIP:    "Strip Glucose mg/dL",
        RECORD_TYPE_ACETONE:  "Ketone mmol/L",

        "4": "", # Rapid-Acting Insulin (units) OR Non-numeric Long-Acting Insulin
        "5": "", # Non-numeric Food
        "6": "",
    }

    with open(filename) as csvfile:
        header = csvfile.readline()
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='|')

        for row in reader:
            entry_ts = row['Device Timestamp']
            entry_type = row['Record Type']
            entry_key = RECORD_TYPES[entry_type]
            entry_name, _, units = entry_key.rpartition(" ")
            if not entry_name: continue

            entry_value = float(row[entry_key])

            INTERESTING_EVENTS = {
                RECORD_TYPE_HISTORIC: CGMEvent,
                RECORD_TYPE_SCAN: ScanEvent,
                RECORD_TYPE_STRIP: StripEvent,
                RECORD_TYPE_ACETONE: AcetoneEvent,
            }
            if entry_type not in INTERESTING_EVENTS:
                continue

            ts = datetime.datetime.strptime(entry_ts, '%d-%m-%Y %H:%M') # eg: 15-07-2021 08:44
            entries[ts].add_event(ts, INTERESTING_EVENTS[entry_type](entry_value, units))


def parse_data(mode):
    results_path = pathlib.Path(common.RESULTS_PATH)  / mode

    parse_tidepool(results_path / "tidepool.json")
    for filename in results_path.glob("*"):
        if filename.suffix == ".csv":
            parse_libreview(filename)
