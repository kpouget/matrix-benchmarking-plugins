import datetime
from collections import defaultdict
import logging
import types

import plotly.graph_objs as go
from dash import html

from matrix_benchmarking.common import Matrix
from matrix_benchmarking.plotting.table_stats import TableStats
import matrix_benchmarking.common as common

from ..store import EventType

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

        for entry in common.Matrix.all_records(settings, setting_lists):
            break

        now = datetime.datetime.now()

        gly_x_y = dict()

        meal_x_y = defaultdict(lambda:defaultdict(float))

        period = cfg.get("start", False), cfg.get("end", False),

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

        current_insulin = None
        current_carbs = None

        insulin_on_board = dict()
        carbs_on_board = dict()

        gly_hourly_diff = {}

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
        for ts, entry in sorted(entry.results.items()):
            if period and ts < period[0]:
                continue

            if period and ts >= period[1]:
                basal_profile_x_y[ts - YOTA] = current_basal_profile
                break

            if basal_ev := entry.get(EventType.BASAL_RATE_ACTUAL):
                if basal_ev.value == 0 or current_basal == 0:
                    basal_interrupted[ts - YOTA] = 0
                    basal_interrupted[ts] = 300
                    basal_interrupted[ts + YOTA] = None

                basal_x_y[ts - YOTA] = current_basal
                current_basal = basal_ev.value * 100
                basal_x_y[ts] = current_basal


            if basal_profile_ev := entry.get(EventType.BASAL_RATE_PROFILE):
                basal_profile_x_y[ts - YOTA] = current_basal_profile
                current_basal_profile = basal_profile_ev.value * 100
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
                    logging.warning(f"{ts} - No bolus glycemia available")
                    bolus_bg = list(gly_x_y.values())[-1]

                try:
                    bolus_ratio = entry.get(EventType.INSULIN_CARB_RATIO).value
                except AttributeError:
                    bolus_ratio = DEFAULT_CARB_RATIO
                    logging.warning(f"{ts} - No carbs/insulin ratio available")

                try:
                    insulin_sensitivity = entry.get(EventType.INSULIN_SENSITIVITY).value
                except AttributeError:
                    logging.warning(f"{ts} - No insulin sensitivity available")
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

                prediction[ts] = current_gly_prediction

                iob[ts] = (current_insulin if current_insulin else 0) + bolus_insulin

            if carbs_ev := entry.get(EventType.CARBS):
                entry_has_carbs = True
                carbs_x_y[ts - YOTA] = 0
                carbs_x_y[ts] = carbs_ev.value
                carbs_x_y[ts + YOTA] = None

                carbs_bg = list(gly_x_y.values())[-1]

                carbs_amount = carbs_ev.value

                cob[ts - YOTA] = current_carbs

                carbs_info = types.SimpleNamespace()
                carbs_info.amount = carbs_amount
                carbs_info.gly = carbs_bg
                carbs_info.is_carbs = True

                carbs_on_board[ts] = carbs_info
                daily_log[ts].append(carbs_info)

                if current_gly_prediction is None:
                    current_gly_prediction = carbs_bg
                    current_gly_prediction_date = ts

                cob[ts] = current_carbs

                prediction[ts] = current_gly_prediction

            if entry_has_carbs and entry_has_bolus:
                basal_study_has_carbs_bolus = True
            elif entry_has_carbs:
                basal_study_has_carbs = True
            elif entry_has_bolus:
                basal_study_has_bolus = True

            if not (bg_ev := entry.get(EventType.GLYCEMIA_CGM)):
                continue

            bg_value = bg_ev.value
            gly_x_y[ts] = bg_value

            def has_carbs_or_insulin():
                if cob[ts] and cob[ts] >= 0.1:
                    return True
                if iob[ts] and iob[ts] >= 0.1:
                    return True
                return False

            def update_basal_study():
                nonlocal basal_study_start_time, basal_study_start_gly

                if basal_study_start_time is None:
                    if not has_carbs_or_insulin():
                        basal_study_start_time = ts
                        basal_study_start_gly = bg_value
                elif has_carbs_or_insulin() or basal_study_start_time.hour != ts.hour:
                    diff = bg_value - basal_study_start_gly
                    gly_hourly_diff[basal_study_start_time + YOTA] = diff
                    gly_hourly_diff[ts - YOTA] = diff
                    if has_carbs_or_insulin():
                        gly_hourly_diff[ts] = None
                        basal_study_start_time = None
                    else:
                        basal_study_start_time = ts
                        basal_study_start_gly = bg_value
                        basal_study_has_carbs_bolus = False
                        basal_study_has_carbs = False
                        basal_study_has_bolus = False

            if insulin_on_board:
                current_insulin = 0
                for bolus_ts, insulin_info in insulin_on_board.copy().items():
                    insulin_age = ts - bolus_ts
                    if insulin_age >= INSULIN_ACTIVITY + YOTA:
                        del insulin_on_board[bolus_ts]
                        continue

                    absorbed_insulin =  insulin_info.amount * insulin_age.total_seconds() * INSULIN_ABSORBTION_RATE_per_seconds
                    current_insulin += insulin_info.amount - absorbed_insulin

                if not insulin_on_board:
                    current_insulin = None
                elif current_insulin < 0.001:
                    if current_insulin > -0.1:
                        current_insulin = 0
                    else:
                        logging.error(f"Insulin on board = {current_insulin} :/ ")
                        logging.error(f"Insulin shots: {insulin_on_board}")
            else:
                current_insulin = None

            if carbs_on_board:
                current_carbs = 0
                for carbs_ts, carbs_info in carbs_on_board.copy().items():
                    carbs_age = ts - carbs_ts

                    absorbed_carbs = carbs_age.total_seconds() * CARBS_ABSORTION_RATE_per_seconds

                    if absorbed_carbs >= carbs_info.amount:
                        del carbs_on_board[carbs_ts]
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

            if current_carbs is not None:
                carbs_delta_seconds = (ts - current_gly_prediction_date).total_seconds()
                try:
                    current_insulin_sensitivity = list(insulin_on_board.values())[-1].sensitivity
                except IndexError:
                    current_insulin_sensitivity = DEFAULT_INSULIN_SENSITIVITY
                    logging.warning(f"{ts} - No insulin sensitivity available")
                try:
                    current_carbs_ratio = list(insulin_on_board.values())[-1].ratio
                except IndexError:
                    current_carbs_ratio = DEFAULT_CARB_RATIO
                    logging.warning(f"{ts} - No carbs/insulin ratio available")

                for carbs_ts, carbs_info in carbs_on_board.copy().items():
                    carbs_delta_seconds = (ts - current_gly_prediction_date).total_seconds()

                    absorbed_carbs = min(current_carbs, carbs_delta_seconds * CARBS_ABSORTION_RATE_per_seconds)

                    new_gly_prediction += (absorbed_carbs / current_carbs_ratio * current_insulin_sensitivity)


            if current_insulin is not None:
                insulin_delta_seconds = (ts - current_gly_prediction_date).total_seconds()

                for bolus_ts, insulin_info in insulin_on_board.copy().items():
                    absorted_insulin = insulin_info.amount * insulin_delta_seconds * INSULIN_ABSORBTION_RATE_per_seconds

                    new_gly_prediction -= absorted_insulin * insulin_info.sensitivity


            prediction[ts] = new_gly_prediction
            cob[ts] = current_carbs
            if not current_carbs: current_carbs = None
            iob[ts] = current_insulin

            current_gly_prediction = new_gly_prediction
            current_gly_prediction_date = ts

            update_basal_study()

        if not gly_x_y:
            return None, "No glycemia :/"

        x_min = x_max = datetime.datetime.now()

        gly_x = list(gly_x_y.keys())
        gly_y = list(gly_x_y.values())

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

        GLY_PROPS = dict(name="Glycemia", line_color="darkgreen", legendgroup="Glycemia")
        fig.add_trace(go.Scatter(x=gly_x, y=gly_y, **GLY_PROPS))

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

        fig.add_trace(go.Scatter(x=gly_x, y=gly_y, **GLY_PROPS, showlegend=False))


        fig.add_trace(go.Scatter(x=list(carbs_x_y.keys()),
                                 y=[(v*1500 if v is not None else None) for v in carbs_x_y.values()],
                                 name=f"Meal",
                                 line_dash="dot",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="coral",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(bolus_x_y.keys()),
                                 y=[(v*500 if v is not None else None) for v in bolus_x_y.values()],
                                 name=f"Bolus",
                                 line_dash="dash",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
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

        fig.add_trace(go.Scatter(x=list(prediction.keys()),
                                 y=list(prediction.values()),
                                 name=f"Glycemie prediction",
                                 visible="legendonly",
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

        fig.add_trace(go.Scatter(x=list(gly_hourly_diff.keys()),
                                 y=list(gly_hourly_diff.values()),
                                 name=f"Gly variation",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="red",
                                 visible="legendonly",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(basal_x_y.keys()),
                                 y=list(basal_x_y.values()),
                                 name=f"Basal administré",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 fill='tozeroy',
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(basal_profile_x_y.keys()),
                                 y=list(basal_profile_x_y.values()),
                                 name=f"Basal prévu",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 line_dash="dot",
                                 mode="lines"))

        fig.add_trace(go.Scatter(x=list(basal_interrupted.keys()),
                                 y=list(basal_interrupted.values()),
                                 name=f"Interruption de basal",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 line_dash="dot",
                                 visible="legendonly",
                                 mode="lines"))

        gly_y_max = max(gly_y)
        gly_y_min = min(gly_y)

        gly_y_max_max = max([gly_y_max] + [v for v in prediction.values() if v])

        fig.update_layout(title=plot_title, title_x=0.5)
        fig.update_layout(yaxis=dict(title=f"Glycémie [{round(gly_y_min)}, {round(gly_y_max)}]",
                                      range=[0, gly_y_max_max*1.05],
                                     ))
        fig.update_layout(xaxis=dict(range=[bod, eod]))

        text = []
        current_meal = None
        for ts, datas in daily_log.items():
            meal_just_printed = False
            meal = ts_to_meal_name(ts)
            if current_meal != meal:
                current_meal = meal
                text.append(html.H3(current_meal.title()))
                current_ts = None
                meal_just_printed = True
            carbs = None
            bolus = None
            for data in datas:
                if hasattr(data, "is_insulin"): bolus = data
                if hasattr(data, "is_carbs"): carbs = data
            gly = bolus.gly if bolus else carbs.gly
            if not meal_just_printed:
                text.append(html.Br())
            text.append(f"{ts.time().strftime('%Hh%M')} | Glycémie à {round(gly)}mg/L, "
                        f"{f'{carbs.amount}g de glucides' if carbs else ''}"
                        f"{' et ' if bolus and carbs else ''}"
                        f"{f'{bolus.amount}u de bolus' if bolus else ''}.")
            text.append(html.Br())

            if bolus:
                if not bolus.target:
                    bolus.target = 150
                    text.append("Pas de cible :/")
                    text.append(html.Br())
                if not bolus.sensitivity:
                    bolus.sensitivity = 150
                    text.append("Pas de sensibilité :/")
                    text.append(html.Br())
                diff = bolus.gly - bolus.target
                text.append(f"Cible à {round(bolus.target)}mg/L => {round(diff):+d}mg/L à corriger")
                text.append(html.Br())

                correction = diff / bolus.sensitivity
                text.append(f"Sensibilité à {round(bolus.sensitivity)}mg/L/u ==> correction de {correction:+.2f}u d'insuline.")
                text.append(html.Br())

                if bolus.iob_pump:
                    correction -= min(correction, bolus.iob_pump)
                    text.append(f"{bolus.iob_pump:.2f}u d'IOB à déduire de la correction ==> correction de {correction:+.2f}u.")
                    text.append(html.Br())
                else:
                    text.append("Pas d'insuline active.")
                    text.append(html.Br())
            else:
                correction = 0

            if carbs and not bolus:
                text.append(f"Glycémie à {round(carbs.gly)}mg/L, {carbs.amount}g de glucides")
                text.append(html.Br())

            if bolus and carbs and carbs.amount:
                carbs_insulin = carbs.amount / bolus.ratio
                text.append(f"{carbs.amount}g de glucides, ratio à {bolus.ratio}g/u => {carbs_insulin:.2f}u")
                text.append(html.Br())
            else:
                carbs_insulin = 0

            if carbs_insulin or correction:
                total = carbs_insulin + correction
                diff = bolus.amount - total
                text.append(f"{carbs_insulin:.2f}u pour les glucides + {correction:.2f}u pour la correction")
                text.append(html.Br())
                text.append(f" ==> {total:.2f}u d'insuline calculé pour {bolus.amount:.2f}u injecté ({diff:+.2f}u d'écart)")

            text.append(html.Br())
        text = None
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
