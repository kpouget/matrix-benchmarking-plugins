import datetime
from collections import defaultdict
import logging
import types

import plotly.graph_objs as go
from dash import html

from matrix_benchmarking.common import Matrix
from matrix_benchmarking.plotting.table_stats import TableStats
import matrix_benchmarking.common as common

from ..store import EventType, TimeRangeType

def register():
    PlotBolusStudy()

YOTA = datetime.timedelta(microseconds=1)
RANGE_LOW = 70
RANGE_HIGH = 180

INSULIN_ACTIVITY = datetime.timedelta(hours=2)
INSULIN_ABSORBTION_RATE_per_seconds = 1 / INSULIN_ACTIVITY.total_seconds()

CARBS_ABSORTION_RATE = 35 # g/hour
CARBS_ABSORTION_RATE_per_seconds = CARBS_ABSORTION_RATE / (60 * 60) # g/s

DEFAULT_CARB_RATIO = 25
DEFAULT_INSULIN_SENSITIVITY = 151

def ts_to_meal_name(ts):
    if ts.time() < datetime.time(7):
        return "nuit"
    elif ts.time() < datetime.time(11):
        return "petit déj"
    elif ts.time() < datetime.time(15):
        return "repas de midi"
    elif ts.time() < datetime.time(19):
        return "gouter"
    elif ts.time() < datetime.time(21):
        return "diner"
    else:
        return "snack de soirée"

class PlotBolusStudy():
    def __init__(self):
        self.name = "Bolus Study"
        self.id_name = self.name.lower().replace(" ", "_")

        TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)


    def do_hover(self, meta_value, variables, figure, data, click_info):
        # would be nice to be able to compute a link to the test results here
        return "nothing"

    def do_plot(self, ordered_vars, settings, setting_lists, variables, cfg):
        fig = go.Figure()
        plot_title = self.name

        bolus_mode = False
        basal_mode = True
        
        for entry in common.Matrix.all_records(settings, setting_lists):
            break

        now = datetime.datetime.now()

        gly_x_y = dict()

        meal_x_y = defaultdict(lambda:defaultdict(float))

        period = cfg.get("start", False), cfg.get("end", False)
        if period:
            period_name = cfg.get("period_name")
            import locale
            locale.setlocale(locale.LC_TIME, 'fr_FR')
            plot_title = period[0].strftime("%A %-d %B") + f" - {period_name}" + f"<br>{plot_title}"

        bolus_x_y = dict()
        carbs_x_y = dict()

        for entry in common.Matrix.all_records(settings, setting_lists):
            break

        daily_log = defaultdict(list)

        target_x_y = dict()
        prediction = dict()
        iob = dict()
        cob = dict()

        current_gly_prediction = None
        current_gly_prediction_date = None
        total_absorbed_insulin = 0
        total_absorbed_carbs = 0
        total_time = 0
        current_insulin = None
        current_carbs = None

        insulin_on_board = dict()
        carbs_on_board = dict()

        insulin_adjustment_x_y = {}

        basal_x_y = {}
        basal_profile_x_y = {}
        current_basal = None
        current_basal_profile = None
        basal_interrupted = {}

        basal_study_start_time = None
        basal_study_start_gly = None
        basal_study_has_carbs_bolus = False
        basal_study_has_carbs = False
        basal_study_has_bolus = False

        current_sensitivity_timerange = {}
        current_basal_timerange = {}
        current_ratio_timerange = {}
        def get_current_range(timerange, ts):
            value = None
            for start, time_value in timerange.items():
                if ts.time() > start:
                    value = time_value
                else:
                    break

            return value
        
        for ts, entry in sorted(entry.results.items()):
            if sensitivity_ev := entry.get(TimeRangeType.INSULIN_SENSITIVITY):
                current_sensitivity_timerange = sensitivity_ev.value
            if ratio_ev := entry.get(TimeRangeType.INSULIN_CARB_RATIO):
                current_ratio_timerange = ratio_ev.value
            if basal_ev := entry.get(TimeRangeType.BASAL):
                current_basal_timerange = basal_ev.value
                
            if period and ts < period[0]:

                if basal_ev := entry.get(EventType.BASAL_RATE_ACTUAL):
                    current_basal = basal_ev.value

                if basal_profile_ev := entry.get(EventType.BASAL_RATE_PROFILE):
                    current_basal_profile = basal_profile_ev.value

                continue

            if period and ts >= period[1]:
                basal_profile_x_y[ts - YOTA] = current_basal_profile
                break
            

            if not basal_x_y:
                basal_x_y[period[0] if period else ts] = current_basal

            if not basal_profile_x_y:
                basal_profile_x_y[period[0] if period else ts] = current_basal_profile
            
            if basal_ev := entry.get(EventType.BASAL_RATE_ACTUAL):
                if basal_ev.value == 0 or current_basal == 0:
                    basal_interrupted[ts - YOTA] = 0
                    basal_interrupted[ts] = 1
                    basal_interrupted[ts + YOTA] = None

                    hypo_info = types.SimpleNamespace()
                    hypo_info.is_hypo = True
                    hypo_info.stopped = basal_ev.value == 0
                    hypo_info.restarted = current_basal == 0
                    hypo_info.basal_rate = basal_ev.value or current_basal
                    hypo_info.gly = list(gly_x_y.values())[-1] \
                        if gly_x_y else 0
                    if not (hypo_info.stopped and hypo_info.restarted):
                        daily_log[ts].append(hypo_info)

                basal_x_y[ts - YOTA] = current_basal
                current_basal = basal_ev.value
                basal_x_y[ts] = current_basal


            if basal_profile_ev := entry.get(EventType.BASAL_RATE_PROFILE):
                basal_profile_x_y[ts - YOTA] = current_basal_profile
                current_basal_profile = basal_profile_ev.value
                basal_profile_x_y[ts] = current_basal_profile

            entry_has_carbs = False
            entry_has_bolus = False
            if bolus_ev := entry.get(EventType.BOLUS):
                entry_has_bolus = True

                bolus_insulin = bolus_ev.value

                bolus_x_y[ts - YOTA] = 0
                bolus_x_y[ts] = bolus_insulin
                bolus_x_y[ts + YOTA] = None

                try:
                    bolus_bg = entry.get(EventType.GLYCEMIA_BOLUS_BASE).value 
                except AttributeError:
                    bolus_bg = list(gly_x_y.values())[-1] \
                        if gly_x_y else 0
                    if not bolus_bg:
                        logging.warning(f"{ts} - No bolus glycemia available.")

                try:
                    bolus_ratio = entry.get(EventType.INSULIN_CARB_RATIO).value
                except AttributeError:
                    bolus_ratio = get_current_range(current_ratio_timerange, ts)
                    if bolus_ratio is None:
                        logging.warning(f"Could not find the ratio for {ts.time()} in {current_ratio_timerange}")
                        bolus_ratio = DEFAULT_CARB_RATIO
                try:
                    insulin_sensitivity = entry.get(EventType.INSULIN_SENSITIVITY).value
                except AttributeError:
                    insulin_sensitivity = get_current_range(current_sensitivity_timerange, ts)
                    if insulin_sensitivity is None:
                        logging.warning(f"Could not find the sensitivity for {ts.time()} in {current_ratio_timerange}")
                        insulin_sensitivity = DEFAULT_INSULIN_SENSITIVITY

                bolus_info = types.SimpleNamespace()
                bolus_info.ratio = bolus_ratio
                bolus_info.amount = bolus_insulin
                bolus_info.sensitivity = insulin_sensitivity
                bolus_info.gly = bolus_bg
                bolus_info.is_insulin = True
                try:
                    bolus_info.iob_pump = entry.get(EventType.INSULIN_ON_BOARD).value
                except AttributeError:
                    bolus_info.iob_pump = None

                try:
                    bolus_info.carbs = entry.get(EventType.CARBS).value
                except AttributeError:
                    bolus_info.carbs = None

                try:
                    bolus_target = entry.get(EventType.GLYCEMIA_BOLUS_TARGET).value
                except AttributeError:
                    bolus_target = None

                bolus_info.target = bolus_target

                insulin_on_board[ts] = bolus_info
                daily_log[ts].append(bolus_info)

                if bolus_info.target:
                    target_x_y[ts - YOTA] = None
                    target_x_y[ts] = bolus_bg
                    target_x_y[ts + INSULIN_ACTIVITY] = bolus_target

                if current_gly_prediction is None:
                    current_gly_prediction_date = ts
                    current_gly_prediction = bolus_bg

                prediction[ts-YOTA] = None
                current_gly_prediction = bolus_bg
                prediction[ts] = current_gly_prediction

                iob[ts] = (current_insulin if current_insulin else 0) + bolus_insulin

            if carbs_ev := entry.get(EventType.CARBS):
                entry_has_carbs = True
                carbs_x_y[ts - YOTA] = 0
                carbs_x_y[ts] = carbs_ev.value
                carbs_x_y[ts + YOTA] = None

                carbs_bg = list(gly_x_y.values())[-1] \
                    if gly_x_y else 0

                carbs_amount = carbs_ev.value

                cob[ts - YOTA] = current_carbs

                carbs_info = types.SimpleNamespace()

                carbs_info.amount = carbs_amount
                carbs_info.gly = carbs_bg
                carbs_info.is_carbs = True

                try:
                    carbs_info.ratio = entry.get(EventType.INSULIN_CARB_RATIO).value
                except AttributeError:
                    carbs_info.ratio = get_current_range(current_ratio_timerange, ts)
                    if carbs_info.ratio is None:
                        logging.warning(f"Could not find the ratio for {ts.time()} in {current_ratio_timerange}")
                        carbs_info.ratio = DEFAULT_CARB_RATIO
                        
                try:
                    carbs_info.insulin_sensitivity = entry.get(EventType.INSULIN_SENSITIVITY).value
                except AttributeError:
                    carbs_info.insulin_sensitivity = get_current_range(current_sensitivity_timerange, ts)
                    if carbs.insulin_sensitivity is None:
                        logging.warning(f"Could not find the sensitivity for {ts.time()} in {current_ratio_timerange}")
                        carbs_info.insulin_sensitivity = DEFAULT_INSULIN_SENSITIVITY
                
                carbs_on_board[ts] = carbs_info
                daily_log[ts].append(carbs_info)

                if current_gly_prediction is None:
                    current_gly_prediction = carbs_bg
                    current_gly_prediction_date = ts

                cob[ts] = (current_carbs if current_carbs else 0) + carbs_amount

                prediction[ts] = current_gly_prediction

            if entry_has_carbs and entry_has_bolus:
                basal_study_has_carbs_bolus = True
            elif entry_has_carbs:
                basal_study_has_carbs = True
            elif entry_has_bolus:
                basal_study_has_bolus = True

            def has_insulin():
                return bool(insulin_on_board)

            def update_basal_study(last=False):
                nonlocal basal_study_start_time, basal_study_start_gly

                if basal_study_start_time is None:
                    if not has_insulin():
                        nonlocal gly_x_y
                        if not gly_x_y: return
                        basal_study_start_time = ts
                        basal_study_start_gly = list(gly_x_y.values())[-1]
                        
                elif last or has_insulin() or basal_study_start_time.hour != ts.hour:
                    gly_diff = bg_value - basal_study_start_gly
                    insulin_diff = gly_diff / DEFAULT_INSULIN_SENSITIVITY
                    if not insulin_adjustment_x_y:
                        insulin_adjustment_x_y[basal_study_start_time] = 0
                        
                    elif list(insulin_adjustment_x_y.values())[-1] is None:
                        insulin_adjustment_x_y[basal_study_start_time] = 0

                    if True: #abs(insulin_diff) >= 0.1:
                        new_basal = 5 * round((current_basal_profile + insulin_diff) * 100 / 5) / 100 # rount to 5 or 10
                        insulin_adjustment_x_y[basal_study_start_time + YOTA] = new_basal
                        insulin_adjustment_x_y[ts - YOTA] = new_basal
                    else:
                        insulin_adjustment_x_y[basal_study_start_time + YOTA] = 0
                        insulin_adjustment_x_y[basal_study_start_time + YOTA + YOTA] = None
                        insulin_adjustment_x_y[ts - YOTA] = None
                        
                    if last or has_insulin():
                        insulin_adjustment_x_y[ts] = 0
                        insulin_adjustment_x_y[ts + YOTA] = None
                        basal_study_start_time = None
                    else:
                        basal_study_start_time = ts
                        basal_study_start_gly = bg_value
                        basal_study_has_carbs_bolus = False
                        basal_study_has_carbs = False
                        basal_study_has_bolus = False

            if not (bg_ev := entry.get(EventType.GLYCEMIA_CGM)):
                update_basal_study()
                continue

            bg_value = bg_ev.value
            gly_x_y[ts] = bg_value
                        
            if insulin_on_board:
                current_insulin = 0
                for bolus_ts, insulin_info in insulin_on_board.copy().items():
                    insulin_age = ts - bolus_ts
                    last_prediction_age = current_gly_prediction_date - bolus_ts
                    if last_prediction_age > INSULIN_ACTIVITY:
                        del insulin_on_board[bolus_ts]
                        continue

                    absorbed_insulin = insulin_info.amount * insulin_age.total_seconds() * INSULIN_ABSORBTION_RATE_per_seconds
                    if absorbed_insulin > insulin_info.amount:
                        absorbed_insulin = insulin_info.amount
                    current_insulin += insulin_info.amount - absorbed_insulin
                
                if current_insulin < 0.001:
                    if current_insulin > -0.1:
                        current_insulin = 0
                    else:
                        logging.error(f"Insulin on board = {current_insulin} :/ ")
                        logging.error(f"Insulin shots: {insulin_on_board}")

            elif current_insulin == 0:
                current_insulin = None

                eob_info = types.SimpleNamespace()
                eob_info.is_end_of_bolus = True
                eob_info.gly = list(gly_x_y.values())[-1]
                daily_log[ts].append(eob_info)
            else:
                current_insulin = None

            if carbs_on_board:
                current_carbs = 0
                for carbs_ts, carbs_info in carbs_on_board.copy().items():
                    carbs_age = ts - carbs_ts
                    last_prediction_age = current_gly_prediction_date - carbs_ts
                    
                    absorbed_carbs = carbs_age.total_seconds() * CARBS_ABSORTION_RATE_per_seconds
                    last_prediction_absorbed_carbs = last_prediction_age.total_seconds() * CARBS_ABSORTION_RATE_per_seconds
                    if last_prediction_absorbed_carbs >= carbs_info.amount:
                        del carbs_on_board[carbs_ts]

                    if absorbed_carbs > carbs_info.amount:
                        absorbed_carbs = carbs_info.amount
                    current_carbs += carbs_info.amount - absorbed_carbs
                    
                if not carbs_on_board:
                    current_carbs = None
    
            if current_carbs is None and current_insulin is None:
                prediction[ts] = None
                iob[ts] = None
                cob[ts] = None

                current_gly_prediction = None
                current_gly_prediction_date = None

                update_basal_study()
                continue

            if not gly_x_y:

                update_basal_study()
                continue

            new_gly_prediction = current_gly_prediction
            prediction_updated = False
            if current_carbs is not None:
                carbs_delta_seconds = (ts - current_gly_prediction_date).total_seconds()

                absorbed_carbs = 0
                
                carbs_delta_seconds = (ts - current_gly_prediction_date).total_seconds()
                for carbs_ts, carbs_info in carbs_on_board.items():
                    absorbed_carbs += carbs_delta_seconds * CARBS_ABSORTION_RATE_per_seconds
                    total_absorbed = (ts - carbs_ts).total_seconds() * CARBS_ABSORTION_RATE_per_seconds
                    absorbed_extra = total_absorbed - carbs_info.amount
                    if absorbed_extra > 0:
                        absorbed_carbs -= absorbed_extra
                
                    total_absorbed_carbs += absorbed_carbs
                    new_gly_prediction += absorbed_carbs / carbs_info.ratio * carbs_info.insulin_sensitivity
                    prediction_updated = True

            if current_insulin is not None and insulin_on_board:
                insulin_delta_seconds = (ts - current_gly_prediction_date).total_seconds()
 
                absorbed_insulin = 0
                for bolus_ts, insulin_info in insulin_on_board.items():
                    bolus_insulin_eol = bolus_ts + INSULIN_ACTIVITY
                    delta_correction = (ts - bolus_insulin_eol).total_seconds() \
                        if ts > bolus_insulin_eol else 0
                    
                    absorbed_insulin += insulin_info.amount * (insulin_delta_seconds - delta_correction) * INSULIN_ABSORBTION_RATE_per_seconds
                
                total_absorbed_insulin += absorbed_insulin

                total_time += insulin_delta_seconds
                new_gly_prediction -= absorbed_insulin * insulin_info.sensitivity
                prediction_updated = True
                
            if prediction_updated:
                prediction[ts] = new_gly_prediction
                
            cob[ts] = current_carbs
            if not current_carbs: current_carbs = None
            iob[ts] = current_insulin

            current_gly_prediction = new_gly_prediction
            current_gly_prediction_date = ts

            update_basal_study()
        
        if not gly_x_y:
            return None, "No glycemia :/"

        update_basal_study(last=True)
        x_min = x_max = datetime.datetime.now()

        gly_x = list(gly_x_y.keys())
        gly_y = list(gly_x_y.values())

        if period:
            if (gly_x[0] - period[0]).total_seconds() / 60 < 30:
                # if first point if less than 30min, do not complete
                gly_x.insert(0, period[0])
                gly_y.insert(0, gly_y[0])

            if (period[1] - gly_x[-1]).total_seconds() / 60 < 30:
                # if last point if less than 30min, do not complete
                gly_x.append(period[1])
                gly_y.append(gly_y[-1])

                basal_x_y[period[1]] = list(basal_x_y.values())[-1]
            else:
                basal_x_y[gly_x[-1]] = list(basal_x_y.values())[-1]
                basal_x_y[gly_x[-1] + YOTA] = 0
                
        if period:
            bod, eod = period
        else:
            bod = datetime.datetime.combine(gly_x[-1], datetime.datetime.min.time())
            eod = datetime.datetime.combine(gly_x[-1], datetime.datetime.max.time())

        fig.add_trace(go.Scatter(x=[bod, eod], y=[RANGE_LOW, RANGE_LOW],
                                 line=dict(width=0),
                                 name="Glycémie normale basse", showlegend=False,
                                 legendgroup="normal",
                                 mode="lines",
                                 ))
        fig.add_trace(go.Scatter(x=[bod, eod], y=[RANGE_HIGH, RANGE_HIGH],
                                 line=dict(width=0),
                                 fill='tonexty',mode="none", fillcolor='rgba(26,150,65,0.2)',
                                 name="Glycémie normale",
                                 legendgroup="normal",
                                 ),)

        def y_out_of_bound(lower_limit, upper_limit):
            above = [_y if _y > upper_limit else upper_limit for _y in gly_y]
            below = [_y if _y < lower_limit else lower_limit for _y in gly_y]

            upper_bound = [upper_limit, upper_limit]
            lower_bound = [lower_limit, lower_limit]

            return above, below, upper_bound, lower_bound

        above_bounds, below_bounds, upper_bound, lower_bound = y_out_of_bound(RANGE_LOW, RANGE_HIGH)

        x_above, x_below = x_out_of_bound(gly_x, gly_y, RANGE_LOW, RANGE_HIGH)

        fig.add_trace(go.Scatter(x=x_above, y=above_bounds, line=dict(width=0), line_color="coral",
                                 showlegend=False, name="Hyperglycemia level", legendgroup="Glycemia range"))

        fig.add_trace(go.Scatter(x=[gly_x[0], gly_x[-1]], y=upper_bound, fill='tonexty',
                                 name="Hyperglycemia", mode="none", legendgroup="Glycemia range",
                                 fillcolor='coral', legendgrouptitle_text="Hyper/hypo Glycemia",))

        # duplicated for 'tonexty' ^^^ to work well
        fig.add_trace(go.Scatter(x=gly_x, y=gly_y,
                                 line=dict(width=0),
                                 showlegend=False, legendgroup="Glycemia range"))

        fig.add_trace(go.Scatter(x=x_below, y=below_bounds, line=dict(width=0),
                                 mode="lines",  legendgroup="Glycemia range",
                                 line_color="darkblue", showlegend=False, name="Hypoglycemia limit"))

        fig.add_trace(go.Scatter(x=[gly_x[0], gly_x[-1]], y=lower_bound, fill='tonexty',
                                 name="Hypoglycemia", mode="lines",
                                 line=dict(width=0),
                                 fillcolor='blue', legendgroup="Glycemia range"))

        fig.add_trace(go.Scatter(x=gly_x, y=gly_y, name="Glycemia", line_color="darkgreen", legendgroup="Glycemia"))

        DASH_COLUMNS_HEIGHT = 350
        
        fig.add_trace(go.Scatter(x=list(carbs_x_y.keys()),
                                 y=[(v and DASH_COLUMNS_HEIGHT if v is not None else None) for v in carbs_x_y.values()],
                                 name=f"Meal",
                                 line_dash="dot",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="coral",
                                 visible="legendonly" if basal_mode else None,
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(bolus_x_y.keys()),
                                 y=[(v and DASH_COLUMNS_HEIGHT if v is not None else None) for v in bolus_x_y.values()],
                                 name=f"Bolus",
                                 line_dash="dash",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 visible="legendonly" if basal_mode else None,
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(prediction.keys()),
                                 y=list(prediction.values()),
                                 name=f"Glycemie prediction",
                                 #visible="legendonly",
                                 hoverlabel={'namelength' :-1},
                                 line=dict(width=2),
                                 line_color="red",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(target_x_y.keys()),
                                 y=list(target_x_y.values()),
                                 name=f"Glycemie target",
                                 hoverlabel={'namelength' :-1},
                                 line=dict(width=4),
                                 line_color="purple",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(iob.keys()),
                                 y=[v * 10 if v is not None else None for v in iob.values()],
                                 name=f"IOB * 10",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(cob.keys()),
                                 y=list(cob.values()),
                                 name=f"COB",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="coral",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(basal_x_y.keys()),
                                 y=[v * 100 if v is not None else None for v in basal_x_y.values()],
                                 name=f"Basal administré * 100",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 fill='tozeroy',
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(basal_profile_x_y.keys()),
                                 y=[v * 100 if v is not None else None for v in basal_profile_x_y.values()],
                                 name=f"Basal prévu * 100",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 line_dash="dot",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(basal_interrupted.keys()),
                                 y=[v and DASH_COLUMNS_HEIGHT for v in basal_interrupted.values()],
                                 name=f"Interruption de basal",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 line_dash="dot",
                                 visible="legendonly",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(insulin_adjustment_x_y.keys()),
                                 y=[v * 100 if v is not None else None for v in insulin_adjustment_x_y.values()],
                                 name=f"Insulin adjustment * 100",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="red",
                                 line_width=2,
                                 #visible="legendonly" ,
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(bolus_x_y.keys()),
                                 y=[(v*10 if v is not None else None) for v in bolus_x_y.values()],
                                 name=f"Insuline shot (*10)",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=12),
                                 line_color="blue",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(carbs_x_y.keys()),
                                 y=list(carbs_x_y.values()),
                                 name=f"Carbs",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=6),
                                 line_color="coral",
                                 mode="lines"))
        
        gly_y_max = max(gly_y)
        y_min = min([0] + [v * 100 for v in insulin_adjustment_x_y.values() if v])
        
        gly_y_max_max = max([gly_y_max] + [v for v in prediction.values() if v] + [239])

        fig.update_layout(title=plot_title, title_x=0.5)
        fig.update_layout(yaxis=dict(title=f"Glycémie",
                                      range=[y_min * 1.05, gly_y_max_max*1.05],
                                     ))

        fig.update_layout(xaxis=dict(range=[bod, eod]))
        want_details = False
        text = []
        current_meal = None
        ongoing_carbs = 0
        ongoing_bolus = 0
        ongoing_bolus_start_time = None
        ongoing_target = 110
        ongoing_sensitivity = 150
        ongoing_ratio = 0
        ongoing_stop = False
        ongoing_extra_correction = 0
        ongoing_extra_carbs = 0
        ongoing_gly_bolus_time = None
        for ts, datas in daily_log.items():
            if period_name == "tout":
                meal = ts_to_meal_name(ts)
                if current_meal != meal:
                    current_meal = meal
                    text.append(html.H3(current_meal.title()))

            carbs = None
            bolus = None
            eob = None
            hypo = None
            for data in datas:
                if hasattr(data, "is_insulin"): bolus = data
                if hasattr(data, "is_carbs"): carbs = data
                if hasattr(data, "is_end_of_bolus"): eob = data
                if hasattr(data, "is_hypo"): hypo = data

            gly = data.gly
            line_header = []
            place_holder = html.Span(line_header)
            text.append(place_holder)
            if carbs:
                text.append(f"{carbs.amount}g de glucides")
                if bolus:
                    text.append(" et ")
                else:
                    text.append("de ressucrage")
                    if ongoing_bolus:
                        ongoing_extra_carbs += carbs.amount
                        text.append("pendant le bolus")
                    else:
                        text.append("hors du bolus")
            if bolus:
                text.append(f"{bolus.amount:.2f}u")
                if carbs:
                    text.append(f"de bolus de repas (ratio à {bolus.ratio}g/u)")
                else:
                    text.append("de correction")
                    ongoing_extra_correction += bolus.amount
                    if ongoing_bolus:
                        text.append("pendant le bolus")
                    else:
                        text.append("hors du bolus")
                        ongoing_gly_bolus_time = bolus.gly

            if eob:
                text.append("fin de l'action de l'insuline")

            if hypo:
                if hypo.stopped:
                    ongoing_stop = ts
                    # text.append(html.B("Arret du basal par la pompe"))
                    # if ongoing_bolus:
                    #     text.append("pendant le bolus")
                    # else:
                    #     text.append("hors du bolus")
                if hypo.restarted and ongoing_stop != False:
                    duration_minutes = (ts - ongoing_stop).total_seconds() / 60
                    duration_hr = duration_minutes / 60
                    avoided_insulin = duration_hr * hypo.basal_rate
                    if duration_minutes > 10:
                        text.append(f"Reprise du basal apres {duration_minutes:.0f} minutes d'arret à {hypo.basal_rate}u/heure, soit {avoided_insulin:.2f}u")

                    if ongoing_bolus:
                        ongoing_extra_correction -= avoided_insulin

            last_val = text.pop()
            if last_val != place_holder:
                text.append(last_val)
                text.append(html.Br())

                line_header.append(f"{ts.time().strftime('%Hh%M')} | Glycémie à {round(gly)}mg/L, ")
                

            if bolus:
                if not ongoing_bolus_start_time:
                    ongoing_bolus_start_time = ts
                if not bolus.target:
                    bolus.target = 150
                    if want_details:
                        text.append("Pas de cible :/")
                        text.append(html.Br())
                ongoing_target = bolus.target

                if not bolus.sensitivity:
                    bolus.sensitivity = 150
                    if want_details:
                        text.append("Pas de sensibilité :/")
                        text.append(html.Br())
                ongoing_sensitivity = bolus.sensitivity

                diff = bolus.gly - bolus.target
                if want_details:
                    text.append(f"Cible à {round(bolus.target)}mg/L => {round(diff):+d}mg/L à corriger")
                    text.append(html.Br())

                correction = diff / bolus.sensitivity
                if want_details:
                    text.append(f"Sensibilité à {round(bolus.sensitivity)}mg/L/u ==> correction de {correction:+.2f}u d'insuline.")
                    text.append(html.Br())

                if bolus.iob_pump:
                    correction -= min(correction, bolus.iob_pump)
                    if want_details:
                        text.append(f"{bolus.iob_pump:.2f}u d'IOB à déduire de la correction ==> correction de {correction:+.2f}u.")
                        text.append(html.Br())
                else:
                    if want_details:
                        text.append("Pas d'insuline active.")
                        text.append(html.Br())
            else:
                correction = 0

            if carbs:
                ongoing_carbs += carbs.amount

            if carbs and not bolus:
                if want_details:
                    text.append(f"Glycémie à {round(carbs.gly)}mg/L, {carbs.amount}g de glucides")
                    text.append(html.Br())

            if bolus and carbs:
                carbs_insulin = carbs.amount / bolus.ratio
                if want_details:
                    text.append(f"{carbs.amount}g de glucides, ratio à {bolus.ratio}g/u => besoin de {carbs_insulin:+.2f}u")
                    text.append(html.Br())
                ongoing_bolus += carbs_insulin
                ongoing_ratio = bolus.ratio
            else:
                carbs_insulin = 0

            if carbs_insulin or correction:
                total = carbs_insulin + correction
                diff = bolus.amount - total
                if want_details:
                    text.append(f"{carbs_insulin:.2f}u pour les glucides + {correction:.2f}u pour la correction")
                    text.append(html.Br())
                    text.append(f" ==> {total:.2f}u d'insuline calculé pour {bolus.amount:.2f}u injecté ({diff:+.2f}u d'écart)")
                    text.append(html.Br())
            if eob:
                diff = eob.gly - ongoing_target
                if want_details:
                    text.append(f"Cible à {ongoing_target:.0f}mg/L. Glycémie à {eob.gly:.0f}mg/L. Différence de {diff:.0f}mg/L")
                    text.append(html.Br())
                correction_required = diff / ongoing_sensitivity
                if want_details:
                    text.append(f"{diff:.0f}mg/L à {ongoing_sensitivity:.0f}mg/L/u => Besoin de {correction_required:+.2f}u d'insuline.")
                    text.append(html.Br())

                new_ratio = None
                if ongoing_bolus:
                    new_ratio = (ongoing_carbs + ongoing_extra_carbs) / (ongoing_bolus + ongoing_extra_correction + correction_required)
                    if want_details:
                        text.append(f"Ratio calculé: {new_ratio:.0f}g/u")
                        text.append(html.Br())
                elif ongoing_extra_correction:
                    new_sensibility =  abs(ongoing_gly_bolus_time - eob.gly) / ongoing_extra_correction
                    if want_details:
                        text.append(f"Paramétres de calcul de la sensibilité: {ongoing_gly_bolus_time:.0f}u pour {abs(ongoing_gly_bolus_time - eob.gly):.0f}mg/L")
                        text.append(html.Br())
                if abs(diff) > 50 or ongoing_extra_correction or ongoing_extra_carbs or ongoing_extra_correction < 0:
                    too_much = False
                    too_low = False

                    if ongoing_extra_correction and ongoing_bolus:
                        text.append(html.B(f"Correction de {ongoing_extra_correction:+.2f}u pendant le bolus."))
                        text.append(html.Br())
                        too_low = True

                    if ongoing_extra_carbs:
                        text.append(html.B(f"Ressucrage de {ongoing_extra_carbs:+.0f}g pendant le bolus."))
                        text.append(html.Br())
                        too_much = True

                    if ongoing_extra_correction < 0:
                        text.append(html.B("Basal temporairement arrêté par la pompe."))
                        text.append(html.Br())
                        too_much = True

                    if ongoing_extra_correction and (ongoing_extra_carbs):
                        text.append(html.I("Correction d'insuline et hypo/ressucrage. Trop compliqué à calculer !"))
                        text.append(html.Br())
                    else:
                        if not new_ratio:
                            text += [f"Glycémie {abs(diff):.0f}mg/L trop {'haute' if diff > 0 else 'basse'} "
                                     f"apres le bolus de {ongoing_bolus_start_time.time().strftime('%Hh%M')}. ",
                                     html.B(f"Sensibilité calculée: {new_sensibility:.0f}mg/L/U"), f"au lieu de {ongoing_sensitivity:.0f}mg/L/u.",
                                     html.Br()
                                     ]
                        elif abs(diff) > 40:
                            text += [f"Glycémie {abs(diff):.0f}mg/L trop {'haute' if diff > 0 else 'basse'} "
                                     f"apres le bolus de {ongoing_bolus_start_time.time().strftime('%Hh%M')}. ",
                                     html.B(f"Ratio calculé: {new_ratio:.0f}g/u"),
                                     f"au lieu de {ongoing_ratio}g/u.",
                                     html.Br()]
                        else:
                            text += [f"Glycemie final à {diff:+.0f}mg/L de la cible, correct.",
                                     html.Br()]

                    if abs(diff) > 20:
                        if new_ratio:
                            if new_ratio < ongoing_ratio: too_low = True
                            if new_ratio > ongoing_ratio: too_much = True
                        else:
                            if diff > 0: too_low = True
                            else: too_much = True

                    if too_much: text += ["==> trop d'insuline dans le bolus", html.Br()]
                    if too_low: text += ["==> pas assez d'insuline dans le bolus", html.Br()]

                else:
                    text += [f"Glycémie {abs(diff):+.0f}mg/L trop {'haute' if diff > 0 else 'basse'}. Bolus correct."]
                    text.append(html.Br())
                    text.append("---")
                text.append(html.Br())
                ongoing_carbs = 0
                ongoing_bolus = 0
                ongoing_bolus_start_time = None
                ongoing_extra_correction = 0
                ongoing_extra_carbs = 0
                ongoing_ratio = 0
                ongoing_gly_bolus_time = None

        return fig, text

def x_out_of_bound(x, y, lower_limit, upper_limit):
    x_above = []
    x_below = []
    for i, (_x1, _y1) in enumerate(zip(x, y)):
        try:
            _x0 = x[i-1]
            _y0 = y[i-1]
        except IndexError:
            _x0 = None
            _y0 = None

        try:
            _x2 = x[i+1]
            _y2 = y[i+1]
        except IndexError:
            _x2 = None
            _y2 = None

        try:
            if not _y0: raise ZeroDivisionError()
            coeff0 = datetime.timedelta(seconds=(_x1-_x0).seconds/(_y1-_y0))
        except ZeroDivisionError:
            coeff0 = datetime.timedelta(seconds=1)

        try:
            if not _y2: raise ZeroDivisionError()
            coeff1 = datetime.timedelta(seconds=(_x2-_x1).seconds/(_y2-_y1))
        except ZeroDivisionError:
            coeff1 = datetime.timedelta(seconds=1)

        if _y2 and _y1 < upper_limit and _y2 > upper_limit:
            # raising from normal* to hyper
            x_above.append(_x1 + coeff1 *(upper_limit-_y1))
        elif _y0 and _y0 < upper_limit and _y1 > upper_limit:
            # raising from normal to hyper*
            x_above.append(_x1)

        elif _y2 and _y1 > upper_limit and _y2 < upper_limit:
            # diving from hyper* to normal
            x_above.append(_x1)
        elif _y0 and _y0 > upper_limit and _y1 < upper_limit:
            # diving from hyper to normal*
            x_above.append(_x0 + coeff0 *(upper_limit-_y0))

        else:
            x_above.append(_x1)


        if _y2 and _y1 < lower_limit and _y2 > lower_limit:
            # raising from hypo* to normal
            x_below.append(_x1)
        elif _y0 and _y0 < lower_limit and _y1 > lower_limit:
            # raising from hypo to normal*
            x_below.append(_x0 + coeff0 *(lower_limit-_y0))

        elif _y2 and _y1 > lower_limit and _y2 < lower_limit:
            # diving from normal* to hypo
            x_below.append(_x1 + coeff1 *(lower_limit-_y1))
        elif _y0 and _y0 > lower_limit and _y1 < lower_limit:
            # diving from normal to hypo*
            x_below.append(_x1)

        else:
            x_below.append(_x1)

    return x_above, x_below
