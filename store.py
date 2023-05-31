import os, sys
import pathlib
from collections import defaultdict
import datetime
import types
from enum import Enum

sys.path.append(os.path.abspath('/home/kevin/vayrac/git/tidepool/data-science-tidepool-api-python'))
from data_science_tidepool_api_python.makedata.tidepool_api import TidepoolAPI

import json
import csv

import matrix_benchmarking.store as store

GLYCEMIA_MMOL_TO_MG = 18.0182

class TimeRange():
    @staticmethod
    def time_from_milliseconds(ms):
        return (datetime.datetime.combine(datetime.date.today(), datetime.time.min)
                + datetime.timedelta(milliseconds=ms)).time()
    
    def __init__(self, ev_type, startTime2value, unit):
        self.ev_type = ev_type
        self.value = startTime2value
        self.unit = unit

    def __str__(self):
        return f"{self.ts} | {self.ev_type}[]"

    def __repr__(self):
        return str(self)

class EventType(Enum):
    KETONE = "ketone"
    CARBS = "carbs"
    BOLUS = "bolus"
    MICRO_BOLUS = "microBolus"
    
    NEW_RESERVOIR = "newReservoir"
    NEW_CATHE = "newCathe"
    INSULIN_CARB_RATIO = "insulinCarbRatio"
    INSULIN_ON_BOARD = "insulinOnBoard"
    INSULIN_SENSITIVITY = "insulineSensitivity"

    BASAL_RATE_ACTUAL = "basalRateActual"
    BASAL_RATE_PROFILE = "basalRateProfile"

    GLYCEMIA_CGM = "cgm"
    GLYCEMIA_SCAN = "scan"
    GLYCEMIA_STRIP = "strip"
    GLYCEMIA_BOLUS_BASE = "bolus base"
    GLYCEMIA_BOLUS_TARGET = "bolus target"

class TimeRangeType(Enum):
    INSULIN_SENSITIVITY = "insulinSensitivity"
    INSULIN_CARB_RATIO = "insulinCarbRatio"
    BASAL = "basal"
    OVERRIDE = "override"
    
class Event():
    def __init__(self, ev_type, value, units):
        self.ev_type = ev_type
        self.value = value
        self.units = units

    def __str__(self):
        return f"{self.ts} | {self.ev_type}[{self.value}{self.units}]"

    def __repr__(self):
        return str(self)

def GlycemiaEvent(ev_type, value, units):
    if units == "mg/dL":
        pass
    elif units == "mmol/L":
        units = "mg/dL"
        value *= 18
    else:
        raise ValueError(f"Unknown {ev_type} glycemia event units: {units} (value={value})")

    return Event(ev_type, value, units)

def BolusGlycemiaEvent(value, units):
    return GlycemiaEvent(EventType.GLYCEMIA_BOLUS_BASE, value, units)

def BolusTargetGlycemiaEvent(value, units):
    return GlycemiaEvent(EventType.GLYCEMIA_BOLUS_TARGET, value, units)

def ActualBasalRateEvent(value):
    return Event(EventType.BASAL_RATE_ACTUAL, value, "u")

def ProfileBasalRateEvent(value):
    return Event(EventType.BASAL_RATE_PROFILE, value, "u")

def CGMEvent(value, units):
    return GlycemiaEvent(EventType.GLYCEMIA_CGM, value, units)

def ScanEvent(value, units):
    return GlycemiaEvent(EventType.GLYCEMIA_SCAN, value, units)

def StripEvent(value, units):
    return GlycemiaEvent(EventType.GLYCEMIA_STRIP, value, units)

def KetoneEvent(value, units):
    return Event(EventType.KETONE, None, value, units)

def InsulineSensitivityEvent(value):
    return Event(EventType.INSULIN_SENSITIVITY, value, "mg/dL /u")

def InsulineOnBoardEvent(value):
    return Event(EventType.INSULIN_ON_BOARD, value, "u")

class Entry():
    def __init__(self):
        self.events = dict()
        self.ts = None

    def add_event(self, ts, event):
        self.events[event.ev_type] = event
        event.ts = ts

    def add_events(self, ts, events):
        for event in events:
            self.add_event(ts, event)

    def get(self, ev_type):
        return self.events.get(ev_type)

    def __str__(self):
        return "["+", ".join(map(str, self.events)) + "]"

    def __repr__(self):
        return str(self)

entries = defaultdict(Entry)

def CarbsEvent(value):
    return Event(EventType.CARBS, value, "g")

def BolusEvent(value):
    return Event(EventType.BOLUS, value, "u")

def MicroBolusEvent(value):
    return Event(EventType.MICRO_BOLUS, value, "u")

def NewReservoirEvent():
    return Event(EventType.NEW_RESERVOIR, 1, "")

def NewCatheEvent():
    return Event(EventType.NEW_CATHE, 1, "")

def CarbsRatioEvent(value):
    return Event(EventType.INSULIN_CARB_RATIO, value, "g/u")

def SensitivityTimeRange(startTime2value):
    return TimeRange(TimeRangeType.INSULIN_SENSITIVITY, startTime2value, "gly/u")

def CarbsRatioTimeRange(startTime2value):
    return TimeRange(TimeRangeType.INSULIN_CARB_RATIO, startTime2value, "g/u")

def BasalTimeRange(startTime2value):
    return TimeRange(TimeRangeType.BASAL, startTime2value, "u/h")

def PumpSettingsOverrideEventTimeRange(overrideType, duration):
    return TimeRange(TimeRangeType.OVERRIDE, overrideType, duration)

def parse_fake():
    entries = defaultdict(Entry)

    ts = datetime.datetime.combine(datetime.datetime.now(), datetime.datetime.min.time())

    midnight = datetime.datetime.combine(datetime.datetime.now(), datetime.datetime.max.time())

    while ts < midnight:
        if ts.time() < datetime.time(hour=6):
            current_gly = 307
        elif ts.time() < datetime.time(hour=12):
            current_gly = 100
        elif ts.time() < datetime.time(hour=18):
            current_gly = 150
        else:
            current_gly = 50

        entries[ts].add_event(ts, CGMEvent(current_gly, "mg/dL"))

        ts += datetime.timedelta(minutes=5)

    ts = datetime.datetime.combine(datetime.datetime.now(),
                                   datetime.time(hour=3))

    entries[ts].add_events(ts, [
        InsulineSensitivityEvent(200),
        BolusEvent(0.98)
    ])

    SENSITIVITY = 150
    for ts_time, carbs, ratio, insulin in (
            (datetime.time(hour=8), 45, 14, None),
            (datetime.time(hour=8, minute=30), 20, 14, None),
            (datetime.time(hour=11, minute=58), 20, 25, 1.92),
            (datetime.time(hour=16), 35, 25, None),
            (datetime.time(hour=19), 15, 25, None),
            ):

        ts = datetime.datetime.combine(datetime.datetime.now(),
                                       ts_time)
        entries[ts].add_events(ts, [
            CarbsEvent(carbs),
            InsulineSensitivityEvent(SENSITIVITY),
            CarbsRatioEvent(ratio),
            BolusEvent(carbs/ratio)
        ])

    return entries

def parse_tidepool(cache_file):
    REFRESH = os.environ.get("MATBENCH_DIAB_TP_REFRESH", False)
    if REFRESH:
        username = os.environ["MATBENCH_DIAB_TP_USERNAME"]
        password = os.environ["MATBENCH_DIAB_TP_PASSWORD"]
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
    TS_PATTERN = '%Y-%m-%dT%H:%M:%S.%fZ'
    TS_PATTERN2 = '%Y-%m-%dT%H:%M:%SZ'
    TS_TIME_PATTERN = '%Y-%m-%dT%H:%M:%S+02:00' # 2021-10-03T10:52:28+02:00
    # http://developer.tidepool.org/data-model/device-data/types/basal/

    for row in user_data:
        if row["type"] == "upload":
            continue
            ts = datetime.datetime.strptime(local_time, TS_TIME_PATTERN) # eg: 2021-09-05T08:45:59.000Z
        local_time = row["deviceTime"]

        ts = datetime.datetime.strptime(local_time, TS_DEVICE_PATTERN) # eg: '2021-10-03T08:50:39.000Z'

        if ts.year != 2023:
            break

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

            entries[ts].add_events(ts, [
                InsulineSensitivityEvent(row.get("insulinSensitivity", 0) * GLYCEMIA_MMOL_TO_MG),
                CarbsRatioEvent(row.get("insulinCarbRatio")),
                InsulineOnBoardEvent(row.get("insulinOnBoard"))
            ])

            if row["carbInput"]:
                entries[ts].add_event(ts,
                                      CarbsEvent(row["carbInput"]))

            if "bgInput" in row and row["bgInput"]:
                entries[ts].add_event(ts,
                                      BolusGlycemiaEvent(row["bgInput"], row["units"]))
            
            try:
                entries[ts].add_event(ts,
                                      BolusTargetGlycemiaEvent(row["bgTarget"]["target"] * GLYCEMIA_MMOL_TO_MG,  "mg/dL"))
            except KeyError: pass
        elif row["type"] == "basal":
# {'deliveryType': 'scheduled',
#  'duration': 240,
#  'localTime': '2021-09-05T08:00:00.000Z',
#  'rate': 0.05,
#  'scheduleName': 'Pattern 1',

            if row["deliveryType"] == "suspend":
                entries[ts].add_event(ts, ActualBasalRateEvent(0))
            else:
                entries[ts].add_event(ts, ActualBasalRateEvent(row["rate"]))
                if "profile_basal_rate" in row["payload"]:
                    entries[ts].add_event(ts, ProfileBasalRateEvent(row["payload"]["profile_basal_rate"]))

            pass

        elif row["type"] == "bolus":
# {'localTime': '2021-09-05T08:46:00.000Z',
#  'normal': 1.1,
#  'subType': 'normal',
            if row["subType"] == "normal":
                if row["normal"] >= 0.05:
                    entries[ts].add_event(ts, BolusEvent(row["normal"]))
                pass
            elif row["subType"] == "automated":
                if row["normal"] >= 0.05:
                    entries[ts].add_event(ts, MicroBolusEvent(row["normal"]))
            elif row["subType"] == "dual/square":
                # {'_deduplicator': {'hash': 'RfyTx5FL2w83YaiAfNotpNo8Z4kGBIjCiJ1p0EEm4Lk='}, 'clockDriftOffset': 0, 'conversionOffset': 0, 'deviceId': 'MMT-1712:NG2629137H', 'deviceTime': '2021-10-16T19:06:58', 'duration': 1740000, 'expectedDuration': 1800000, 'expectedExtended': 0.3, 'extended': 0.3, 'id': '7042a4c2a89e1f5f25e0460b044ee749', 'normal': 0.2, 'payload': {'logIndices': [2155727818]}, 'revision': 1, 'subType': 'dual/square', 'time': '2021-10-16T17:06:58.000Z', 'timezoneOffset': 120, 'type': 'bolus', 'uploadId': '770530ce3b3d97fc4f0ebb0d0bdd2a2f'}
                pass
            else:
                print(row)
                import pdb;pdb.set_trace()
                pass
            pass
        elif row["type"] in ("cbg, ""smbg"):

            # Self-Monitored Blood Glucose
# {'localTime': '2021-09-05T08:45:59.000Z',
#  'subType': 'manual',
#  'units': 'mg/dL',
#  'value': 77.9999381522}
            if "subType" not in row:
                try:
                    ts = datetime.datetime.strptime(row["deviceTime"], TS_DEVICE_PATTERN) # eg: 2021-09-05T08:45:59Z
                except:
                    ts = datetime.datetime.strptime(row["time"], TS_PATTERN) # eg: 2021-09-05T08:45:59Z
                if "deviceId" not in row:
                    continue
                if "FreeStyle" in row["deviceId"]:
                    continue

                entries[ts].add_event(ts, CGMEvent(row["value"], row["units"]))

            elif row["subType"] == "manual":
                # coverted by wizard
                pass
            elif row["subType"] == "linked":
                # ignore
                pass
            else:
                print(row)
            pass
        elif row["type"] == "pumpSettings":
            # row["carbRatio"]
            if "carbRatio" in row:
                startTime2value = {}
                for ratio in row["carbRatio"]:
                    start_time = TimeRange.time_from_milliseconds(ratio["start"])
                    value = ratio["amount"]
                    startTime2value[start_time] = value
                entries[ts].add_event(ts, CarbsRatioTimeRange(startTime2value))
                del row["carbRatio"]

            # row["basalSchedules"]
            for basal_pattern, basal_sched in row["basalSchedules"].items():
                startTime2value = {}
                for basal in basal_sched:
                    start_time = TimeRange.time_from_milliseconds(basal["start"])
                    value = basal["rate"]
                    startTime2value[start_time] = value
                entries[ts].add_event(ts, BasalTimeRange(startTime2value))
            del row["basalSchedules"]

            # row["activeSchedule"]
            # Pattern 1

            # row["basal"]
            # {'rateMaximum': {'units': 'Units/hour', 'value': 2}}

            # row["bolus"]
            # {'amountMaximum': {'units': 'Units', 'value': 10}, 'calculator': {'enabled': True, 'insulin': {'duration': 120, 'units': 'minutes'}}, 'extended': {'enabled': False}}

            # insulinSensitivity
            # [{'amount': 11.1015, 'start': 0}]
            if "insulinSensitivities" in row:
                name, = row["insulinSensitivities"].keys()
                values, = row["insulinSensitivities"].values()
                startTime2value = {}
                for sensitivityRange in values:
                    start_time = TimeRange.time_from_milliseconds(sensitivityRange["start"])
                    value = sensitivityRange["amount"]
                    startTime2value[start_time] = value * GLYCEMIA_MMOL_TO_MG
                entries[ts].add_event(ts, SensitivityTimeRange(startTime2value))
                del row["insulinSensitivities"]

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
                    print(row)
            elif row["subType"] == "status":
                if row["status"] == "suspended":
                    # future work
                    # {"logIndices":[2152442090],"resumed":{"cause":"User resumed"},"suspended":{"cause":"User suspend"}}
                    # {"logIndices":[2152336490],"resumed":{"cause":"User resumed"},"suspended":{"cause":"Set change suspend"}}
                    pass
                elif row["status"] == "resumed":
                    # {'annotations': [{'code': 'status/unknown-previous'}], 'clockDriftOffset': 0, 'conversionOffset': 0, 'deviceId': 'tandem1002717942134', 'deviceTime': '2023-03-20T23:04:39', 'guid': 'ba724b9e-74d0-4d49-ac4c-e1bb75716c5d', 'id': 'tg50ad2kb9e1i1pl38ka49strl9phd8u', 'payload': {'logIndices': [15200]}, 'reason': {'resumed': 'automatic'}, 'status': 'resumed', 'subType': 'status', 'time': '2023-03-20T22:04:39Z', 'timezoneOffset': 60, 'type': 'deviceEvent', 'uploadId': 'upid_61c584ea0947'}
                    pass
                else:
                    print(row) 
            elif row["subType"] == "alarm":
                # {'alarmType': 'other', 'clockDriftOffset': 46000, 'conversionOffset': 0, 'deviceId': 'tandem1002717942134', 'deviceTime': '2023-03-25T19:24:47', 'guid': 'ab9567e6-0339-4871-9615-e15a1fffe113', 'id': 'mvd2i4os6qaecg1bhnhntr6n7eaouhvh', 'payload': {'alert_id': 48, 'logIndices': [25642]}, 'subType': 'alarm', 'time': '2023-03-25T18:24:47Z', 'timezoneOffset': 60, 'type': 'deviceEvent', 'uploadId': 'upid_48ad1e0597e2'}
                pass
            elif row["subType"] == "calibration":
            # {'clockDriftOffset': 0, 'conversionOffset': 0, 'deviceId': 'tandem1002717942134', 'deviceTime': '2023-03-22T22:22:46', 'guid': 'ec9956d5-8c2d-44dd-8d05-c7f0d490e548', 'id': 'm3s0oedo2kp4i2e8098qb2u6bdou6352', 'payload': {'logIndices': [19723]}, 'subType': 'calibration', 'time': '2023-03-22T21:22:46Z', 'timezoneOffset': 60, 'type': 'deviceEvent', 'units': 'mmol/L', 'uploadId': 'upid_29041b1bcc8e', 'value': 16.374706573584323}

                pass
            elif row["subType"] == "timeChange":
# { "change": {
#     "agent": "manual",
#     "from": "2023-03-27T06:32:46",
#     "to": "2023-03-27T07:32:00"
#   },
#   "clockDriftOffset": 0,
#   "conversionOffset": 0,
#   "deviceId": "tandem1002717942134",
#   "deviceTime": "2023-03-27T07:32:00",
#   "guid": "b51eee61-6ad1-44de-95da-daff58131d7f",
#   "id": "bvjtovbpddijifmmj8pou4puluon7lcg",
#   "payload": {
#     "logIndices": [
#       28384
#     ]
#   },
#   "subType": "timeChange",
#   "time": "2023-03-27T05:32:00Z",
#   "timezoneOffset": 120,
#   "type": "deviceEvent",
#   "uploadId": "upid_48ad1e0597e2"}
                pass
            elif row["subType"] == "pumpSettingsOverride":
                PumpSettingsOverrideEventTimeRange(row["overrideType"], row["duration"])
                
            else:
                print(row)
                import pdb;pdb.set_trace()
            pass
        elif row["type"] == "food":
            # {'clockDriftOffset': 0, 'conversionOffset': 0, 'deviceId': 'tandem1002717942134', 'deviceTime': '2023-03-14T12:32:57', 'guid': '070d5b94-b0b4-49d4-8e82-e3e6445c2309', 'id': 'hhh7vj4ia6b21ru3hnmbh3bicv1msc2l', 'nutrition': {'carbohydrate': {'net': 20, 'units': 'grams'}}, 'payload': {'logIndices': [489], 'sourceType': 'Local pump entry'}, 'time': '2023-03-14T11:32:57Z', 'timezoneOffset': 60, 'type': 'food', 'uploadId': 'upid_d2a0652509d1'}

            pass
        elif row["type"] == "bloodKetone":
            # {'_deduplicator': {'hash': 'th3WxMzjzkKdMHlH0JY13DvH3Z2WXLyyMky9W1iRtQQ='}, 'clockDriftOffset': 0, 'conversionOffset': 0, 'deviceId': 'AbbottFreeStyleLibre2-MBGA161-G1265', 'deviceTime': '2021-07-17T12:10:00', 'id': '212898083d3b0c21f5d00bc3749b6b7b', 'payload': {'logIndices': [70368]}, 'revision': 1, 'time': '2021-07-17T10:10:00Z', 'timezoneOffset': 120, 'type': 'bloodKetone', 'units': 'mmol/L', 'uploadId': 'd816647185e128eb5d0e51ce7f327ae7', 'value': 0.1}
            entries[ts].add_event(ts, KetoneEvent(row["value"], row["units"]))

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
            print(f"type: {row.get('type')}")
            print(f"subtype: {row.get('subType')}")
            print(row)

    return entries


def parse_data():
    results_path = pathlib.Path("/home/kevin/vayrac/git/matbench_diab/data")

    FAKE = os.environ.get("MATBENCH_DIAB_FAKE", False)
    print("MATBENCH_DIAB_FAKE=", FAKE)
    if FAKE:
        results = parse_fake()
    else:
        results = parse_tidepool(results_path / "tidepool.json")

    store.add_to_matrix(dict(loaded=True),
                        results_path,
                        results,
                        None)
