import copy
import datetime

import plotly.graph_objs as go
from dash import html
from dash import dcc

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common

def register():
    for period in PERIODS:
        BolusReport(period)

def set_vars(additional_settings, ordered_vars, settings, param_lists, variables, cfg):
    _settings = dict(settings)
    _variables = copy.deepcopy(variables)
    _ordered_vars = list(ordered_vars)
    for k, v in additional_settings.items():
        _settings[k] = v
        _variables.pop(k, True)
        if k in _ordered_vars:
            _ordered_vars.remove(k)

    _param_lists = [[(key, v) for v in variables[key]] for key in _ordered_vars]

    return _ordered_vars, _settings, _param_lists, _variables, cfg

def set_config(additional_cfg, args):
    cfg = copy.deepcopy(args[-1])
    cfg.d.update(additional_cfg)
    return list(args[:-1]) + [cfg]

def set_entry(entry, _args):
    args = copy.deepcopy(_args)
    ordered_vars, settings, setting_lists, variables, cfg = args

    settings.update(entry.settings.__dict__)
    setting_lists[:] = []
    variables.clear()
    return args

def set_filters(filters, _args):
    args = copy.deepcopy(_args)
    ordered_vars, settings, setting_lists, variables, cfg = args

    for filter_key, filter_value in filters.items():
        if filter_key in variables:
            variables.pop(filter_key)
        settings[filter_key] = filter_value

        for idx, setting_list_entry in enumerate(setting_lists):
            if setting_list_entry[0][0] == filter_key:
                del setting_lists[idx]
                break

    return args

def Plot(name, args, msg_p=None):
    stats = table_stats.TableStats.stats_by_name[name]
    fig, msg = stats.do_plot(*args)
    if msg_p is not None: msg_p.append(msg)

    return dcc.Graph(figure=fig)

def Plot_and_Text(name, args):
    msg_p = []

    data = [Plot(name, args, msg_p)]

    if msg_p[0]:
        data.append(
            html.Div(
                msg_p[0],
                style={"border-radius": "5px",
                       "padding": "0.5em",
                       "background-color": "lightgray",
                       }))
    else:
        data.append(None)
        
    return data

PERIODS = "matin", "midi", "gouter", "diner", "nuit", "tout"

def get_time_range(date, day_index, range_name):
    start_day = datetime.datetime.combine(
        date - datetime.timedelta(days=day_index),
        datetime.datetime.min.time()) # midnight morning

    match range_name:
      case "matin":
        start_date = datetime.datetime.combine(start_day, datetime.time(hour=6))
        end_date = datetime.datetime.combine(start_date, datetime.time(hour=12))

      case "midi":
        start_date = datetime.datetime.combine(start_day, datetime.time(hour=11, minute=30))
        end_date = datetime.datetime.combine(start_date, datetime.time(hour=15, minute=30))

      case "gouter":
        start_date = datetime.datetime.combine(start_day, datetime.time(hour=15, minute=30))
        end_date = datetime.datetime.combine(start_date, datetime.time(hour=19, minute=00))

      case "diner":
        start_date = datetime.datetime.combine(start_day, datetime.time(hour=18, minute=30))
        end_date = datetime.datetime.combine(start_date, datetime.time(hour=22, minute=30))

      case "nuit":
        start_date = datetime.datetime.combine(start_day, datetime.time(hour=18))
        end_date = datetime.datetime.combine(start_date + datetime.timedelta(days=1), datetime.time(hour=7))

      case "tout" | _:
        start_date = start_day
        end_date = start_date + datetime.timedelta(days=1)

    return start_date, end_date


class BolusReport():
    def __init__(self, period):
        self.period = period
        self.name = f"bolus report: {self.period}"
        self.id_name = self.name.lower().replace(" ", "_")
        self.no_graph = True
        self.is_report = True

        table_stats.TableStats._register_stat(self)

    def do_plot(self, *args):
        START = 0
        DAYS = 7

        header = []

        ordered_vars, settings, setting_lists, variables, cfg = args

        for entry in common.Matrix.all_records(settings, setting_lists):
            break

        last_record_day = list(entry.results)[0]

        header += [html.H1(f"Bolus Study - {self.period}")]
        header += [html.H2(f"Résumé")]
        summary = []
        header += [html.Span(summary)]
        plots = []
        time_period = [None, None]
        for i in range(START, START+DAYS):
            start_date, end_date = get_time_range(last_record_day, i, self.period)
            if time_period[1] is None:
                time_period[1] = end_date
            time_period[0] = start_date
            header += [html.H2(start_date.date())]
            plot, text = Plot_and_Text(f"Bolus Study", set_config(dict(start=start_date, end=end_date, period_name=self.period), args))
            header += [plot, text]
            plots += [[plot, text]]

        summary += generate_summary(plots, self.period, time_period)
        return None, header


def generate_summary(plots, period_name, period):
    fig = go.Figure()
    plot_title = f"Résumé {period_name} sur { (period[1] - period[0]).days + 1} jours<br>{period[0].date()} - {period[1].date()}"

    y_min = 0
    first = True

    headers = []
    for plot, text in plots:
        for _data in plot.figure.data:
            data = copy.deepcopy(_data)
            keep = data.name in [
                "Glycemia",
                "Insuline shot (*10)", "Carbs",
                #"Meal", "Bolus",
                "Insulin adjustment * 100",
                "IOB * 10",
                "Basal administré * 100"
            ]
            is_normale = bool(first and data.name and ("normale" in data.name))
            keep |= is_normale

            if not keep:
                continue
            
            date = list(data.x)[0].date()
            day_offset = date - period[0].date()
            data.legendgroup = str(date)
            import locale
            locale.setlocale(locale.LC_TIME, 'fr_FR')
            data.legendgrouptitle.text = date.strftime("%A %-d %B")
            if not is_normale:
                data.fill = None
                #data.line.color = None

            data.x = [d - day_offset for d in data.x]
            fig.add_trace(data)
            y_min = min([y_min] + [y for y in data.y if y is not None])

        headers += [html.H2(str(date))]

        def process_line(line):
            nonlocal headers
            keep = "Ratio calculé" in str(line)
            keep |= "Sensibilité calculé" in str(line)
            if not keep: return
            headers += line
            headers += [html.Br()]
        
        current_line = []
        for child in text.children:
            if not isinstance(child, html.Br):
                current_line.append(child)
                continue
            
            process_line(current_line)
            current_line = []
                
        first = False
            
    fig.update_layout(title=plot_title, title_x=0.5)
    fig.update_layout(yaxis=dict(title=f"Glycémie",
                                 range=[y_min, 420],
                                 ))
    
    #fig.update_layout(xaxis=dict(range=[period[0].time(), period[1].time()]))
        
    return  dcc.Graph(figure=fig), html.Div(
                headers,
                style={"border-radius": "5px",
                       "padding": "0.5em",
                       "background-color": "lightgray",
                       })
