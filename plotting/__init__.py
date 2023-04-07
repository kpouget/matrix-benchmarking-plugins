import datetime
from collections import defaultdict

import plotly.graph_objs as go

from matrix_benchmarking.common import Matrix
from matrix_benchmarking.plotting.table_stats import TableStats
import matrix_benchmarking.common as common

from . import report
from . import bolus

report.register()
bolus.register()

YOTA = datetime.timedelta(microseconds=1)

PERIODS = {
    "3 days": 3,
    "7 days": 8,
    "14 days": 14,
    "1 month": 30,
    "3 months": 90,
}

def ts_to_meal_name(ts):
    if ts.time() < datetime.time(7):
        return "snack de nuit"
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

def ts_to_day_period(ts):
    if ts.time() < datetime.time(7):
        return "6. matinée"
    elif ts.time() < datetime.time(11):
        return "1. matin"
    elif ts.time() < datetime.time(15):
        return "2. midi"
    elif ts.time() < datetime.time(19):
        return "3. gouter"
    elif ts.time() < datetime.time(21):
        return "4. diner"
    else:
        return "5. soirée"

def register():
    PlotInsulineChanges()

    PlotOverview()
    PlotDailySummary("carbs")
    PlotDailySummary("carbs", in_pct=True)

    #for idx, period in enumerate(PERIODS):
    #Matrix.settings["Period"].add(f"{idx}) {period}")

class PlotOverview():
    def __init__(self):
        self.name = "Diabetes Overview"
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
        GLY_PROPS = {
            "cgm": dict(name="Continue", line_color="darkgreen"),
            "scan": dict(name="Scan", mode="markers", marker_color="green"),
            "strip": dict(name="Strip", mode="markers"),
            "acetone": dict(name="acetone", mode="markers+lines", line=dict(width=5), marker_color="cornflowerblue"),
        }

        period = 8
        now = datetime.datetime.now()

        gly_x = defaultdict(list)
        gly_y = defaultdict(list)

        gly_y_max = 0
        gly_y_min = 200

        meal_x_y = defaultdict(lambda:defaultdict(float))

        current_meal_ratio = defaultdict(int)
        current_meal_ratiodiff = defaultdict(int)
        ch_ratio_min = 0

        meals = defaultdict(dict)

        reservoir = dict()
        ts_prev_reservoir = None
        days_since_prev_reservoir = 0

        period = cfg.get("start", False), cfg.get("end", False),

        bolus = dict()
        cathe = dict()
        ts_prev_cathe = None
        days_since_prev_cathe = 0
        for entry in common.Matrix.all_records(settings, setting_lists):
            break
        for ts, entry in sorted(entry.results.items()):
            for event in entry.events:
                meal = ts_to_meal_name(ts)

                if event.ev_type == "newReservoir":
                    if ts_prev_reservoir:
                        diff = ts - ts_prev_reservoir
                        days_since_prev_reservoir = diff.days + diff.seconds/60/60/24
                    ts_prev_reservoir = ts

                if event.ev_type == "newCathe":
                    if ts_prev_cathe:
                        diff = ts - ts_prev_cathe
                        days_since_prev_cathe = diff.days + diff.seconds/60/60/24
                    ts_prev_cathe = ts

                if event.ev_type == "carbsRatio":

                    event_day = datetime.datetime.combine(ts.date(), datetime.datetime.min.time())

                    if current_meal_ratio[meal] != event.value:
                        current_meal_ratiodiff[meal] = (current_meal_ratio[meal] - event.value) * 10
                        current_meal_ratio[meal] = event.value
                        #print(ts, meal, "> CHANGED", current_meal_ratio[meal], event.value)

                if period and not (ts > period[0] and ts < period[1]):
                        continue

                if event.ev_type == "newReservoir":
                    reservoir[ts] = days_since_prev_reservoir

                if event.ev_type == "newCathe":
                    cathe[ts] = days_since_prev_cathe

                if event.ev_type == "carbsRatio":
                    meal_x_y[meal][ts - YOTA] = 0
                    meal_x_y[meal][ts] = current_meal_ratiodiff[meal]
                    ch_ratio_min = min([ch_ratio_min, meal_x_y[meal][ts]])
                    meal_x_y[meal][ts + YOTA] = None

                if event.ev_type == "bolus":
                    bolus[ts - YOTA] = 0
                    bolus[ts] = event.value * 100
                    bolus[ts + YOTA] = None
                    pass

                if event.ev_type == "carbs":
                    meals[meal][ts - YOTA] = 0
                    meals[meal][ts] = event.value
                    meals[meal][ts + YOTA] = None

                if event.ev_type in GLY_PROPS:
                    if event.ev_type == "acetone":
                        gly_x[event.ev_type].append(ts - YOTA)
                        gly_y[event.ev_type].append(0)

                    gly_x[event.ev_type].append(ts)
                    gly_y[event.ev_type].append(event.value)

                    if event.ev_type == "scan":
                        gly_x["cgm"].append(ts)
                        gly_y["cgm"].append(event.value)

                    if event.ev_type == "acetone":
                        gly_x[event.ev_type].append(ts - YOTA)
                        gly_y[event.ev_type].append(0)
                        gly_x[event.ev_type].append(ts + YOTA)
                        gly_y[event.ev_type].append(None)
                else:
                    continue

                gly_y_max = max([event.value, gly_y_max])
                gly_y_min = min([event.value, gly_y_min])

        first = True
        x_min = x_max = datetime.datetime.now()
        for ev_type in GLY_PROPS:
            if ev_type not in gly_x: continue
            x = gly_x[ev_type]
            y = gly_y[ev_type]

            if first:
                fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[80, 80],
                                         line=dict(width=0), showlegend=False,
                                         name="Glycémie normale basse",
                                         legendgroup="cgm",
                                         ))
                fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[150, 150],
                                         line=dict(width=0), showlegend=False,
                                         fill='tonexty',mode="none", fillcolor='rgba(26,150,65,0.2)',
                                         name="Glycémie normale haute",
                                         legendgroup="cgm",
                                         ),)
                first = False
                x_min = min(x)
                x_max = max(x)
            else:
                x_min = min(x + [x_min])
                x_max = max(x + [x_max])

            fig.add_trace(go.Scatter(x=x, y=y, **GLY_PROPS[ev_type], legendgroup=ev_type))
            if ev_type == "cgm":
                def y_out_of_bound(lower_limit, upper_limit):
                    above = [_y if _y > upper_limit else upper_limit for _y in y]
                    below = [_y if _y < lower_limit else lower_limit for _y in y]

                    upper_bound = [upper_limit, upper_limit]
                    lower_bound = [lower_limit, lower_limit]

                    return above, below, upper_bound, lower_bound

                above_bounds, below_bounds, upper_bound, lower_bound = y_out_of_bound(80, 150)

                def x_out_of_bound(lower_limit, upper_limit):
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

                x_above, x_below = x_out_of_bound(80, 150)

                fig.add_trace(go.Scatter(x=x_above, y=above_bounds, line=dict(width=0), showlegend=False, legendgroup=ev_type, name="Hyperglycémie"))
                fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=upper_bound, fill='tonexty', name="Limite d'hyperglycemie", mode="none", fillcolor='coral', showlegend=False, legendgroup=ev_type))

                fig.add_trace(go.Scatter(x=x, y=y, **GLY_PROPS[ev_type], showlegend=False, legendgroup=ev_type))
                fig.add_trace(go.Scatter(x=x_below, y=below_bounds, line=dict(width=0), showlegend=False,  mode="lines", legendgroup=ev_type, line_color="darkblue", name="Hypoglycemie"))
                fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=lower_bound, fill='tonexty', name="Limite d'hypoglycemie", mode="lines", fillcolor='blue', showlegend=False, legendgroup=ev_type))
                fig.add_trace(go.Scatter(x=x, y=y, **GLY_PROPS[ev_type], showlegend=False, legendgroup=ev_type))


        for meal in meals:
            fig.add_trace(go.Scatter(x=list(meals[meal].keys()),
                                     y=list(meals[meal].values()),
                                     name=f"Repas {meal}",
                                     legendgroup=meal,
                                     hoverlabel= {'namelength' :-1},
                                     line=dict(width=4),
                                     line_color="black",
                                     mode="lines"))

        fig.add_trace(go.Scatter(x=list(bolus.keys()),
                                 y=list(bolus.values()),
                                 name=f"Insuline",
                                 hoverlabel= {'namelength' :-1},
                                 line=dict(width=1),
                                 line_color="blue",
                                 mode="lines"))

        # for meal in sorted(meal_x_y):
        #     name = f"Changement de ratio {meal}"
        #     fig.add_trace(go.Scatter(x=list(meal_x_y[meal].keys()),
        #                              y=list(meal_x_y[meal].values()),
        #                              name=name,
        #                              legendgroup=meal,
        #                              hoverlabel= {'namelength' :-1},
        #                              line=dict(width=5),
        #                              mode="lines"))

        # fig.add_trace(go.Scatter(x=list(reservoir.keys()),
        #                          y=list(reservoir.values()),
        #                          name=f"Changement reservoir",
        #                          hoverlabel= {'namelength' :-1},
        #                          marker=dict(size=20),
        #                          marker_color="green",
        #                          line_width=0.5,
        #                          mode="markers+lines"))

        # fig.add_trace(go.Scatter(x=list(cathe.keys()),
        #                          y=list(cathe.values()),
        #                          name=f"Changement cathé",
        #                          hoverlabel= {'namelength' :-1},
        #                          marker=dict(size=10),
        #                          marker_color="blue",
        #                          line_width=0.5,
        #                          mode="markers+lines"))

        fig.update_layout(title=plot_title, title_x=0.5)
        # fig.update_layout(yaxis=dict(title=f"Level [{gly_y_min}, {gly_y_max}]",
        #                              range=[ch_ratio_min, gly_y_max*1.05],
        #                              ))
        fig.update_layout(xaxis=dict(range=[x_min - datetime.timedelta(hours=1), x_max + datetime.timedelta(hours=1)],
                                     ))
        return fig, ""

class PlotDailySummary():
    def __init__(self, what, *, in_pct=False):
        self.what = what
        self.in_pct = in_pct

        self.name = f"{self.what.title()} Daily Summary" + (" (pct)" if self.in_pct else "")
        self.id_name = self.name.lower().replace(" ", "_")

        TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        # would be nice to be able to compute a link to the test results here
        return "nothing"

    def do_plot(self, ordered_vars, settings, setting_lists, variables, cfg):
        fig = go.Figure()
        plot_title = self.name

        period = 8
        now = datetime.datetime.now()

        x = []
        day_periods_y = defaultdict(lambda:defaultdict(int))
        day_periods = set()
        day_periods_total = defaultdict(int)

        for entry in common.Matrix.all_records(settings, setting_lists):
            break
        for ts, entry in sorted(entry.results.items()):
            for event in entry.events:
                if period and (now - ts).days > period: continue

                if event.ev_type != self.what:
                    continue
                #print(event)
                x.append(ts.date())
                day_period = ts_to_day_period(ts)
                day_periods.add(day_period)
                day_periods_y[day_period][ts.date()] += event.value
                day_periods_total[ts.date()] += event.value

        prev = [0 for _ in x]
        for day_period in sorted(day_periods):
            if self.in_pct:
                y = [day_periods_y[day_period][_x]/day_periods_total[_x] * 100for _x in x]
            else:
                y = [day_periods_y[day_period][_x] for _x in x]

            fig.add_trace(go.Scatter(x=x, y=y,
                                     name=day_period,
                                     mode="lines+markers",
                                     stackgroup='one'))

        fig.update_layout(title=plot_title, title_x=0.5)
        #fig.update_layout(yaxis=dict(title=f"Level [{gly_y_min}, {gly_y_max}]",
        #                             range=[0, gly_y_max*1.05],
        #                             ))
        #fig.update_layout(xaxis=dict(range=[x_min - datetime.timedelta(hours=1), x_max + datetime.timedelta(hours=1)],
        #                             ))
        return fig, ""

class PlotInsulineChanges():
    def __init__(self):
        self.what = "Insuline changes"

        self.name = f"{self.what.title()}"
        self.id_name = self.name.lower().replace(" ", "_")

        TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        # would be nice to be able to compute a link to the test results here
        return "nothing"

    def do_plot(self, ordered_vars, settings, setting_lists, variables, cfg):
        fig = go.Figure()
        plot_title = self.name

        if settings["Period"] == "---":
            period = 0
        else:
            period = PERIODS[settings["Period"].partition(" ")[-1]]
            now = datetime.datetime.now()

        MEAL_TIMES = {
            "petit déj": 8,
            "déj": 12,
            "gouter": 16,
            "diner": 19
        }
        meal_x_y = defaultdict(lambda:defaultdict(float))

        maxi = 0
        current_meal_value = defaultdict(int)
        for entry in common.Matrix.all_records(settings, setting_lists):
            break
        for ts, entry in sorted(entry.results.items()):
            for event in entry.events:
                if period and (now - ts).days > period: continue

                if event.ev_type == "carbsRatioRange":
                    event_day = datetime.datetime.combine(ts.date(), datetime.datetime.min.time())

                    for meal, time in MEAL_TIMES.items():
                        if (event_day + event.start_time) < (event_day + datetime.timedelta(hours=time)):
                            current_meal_value[meal] = event.value
                            maxi = max([maxi, event.value])
                for meal in MEAL_TIMES:
                    meal_x_y[meal][ts.date()] = current_meal_value[meal]

        for meal in MEAL_TIMES:
            fig.add_trace(go.Scatter(x=list(meal_x_y[meal].keys()),
                                     y=list(meal_x_y[meal].values()),
                                     name=meal,
                                     mode="lines"))

        fig.update_layout(title=plot_title, title_x=0.5)
        fig.update_layout(yaxis=dict(title=f"Ratio glucides]",
                                     range=[0, maxi*1.05],
                                     ))
        #fig.update_layout(xaxis=dict(range=[x_min - datetime.timedelta(hours=1), x_max + datetime.timedelta(hours=1)],
        #                             ))
        return fig, ""
