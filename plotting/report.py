import copy
import datetime

from dash import html
from dash import dcc

import matrix_benchmarking.plotting.table_stats as table_stats
import matrix_benchmarking.common as common

def register():
    BolusReport()

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

    return data

class BolusReport():
    def __init__(self):
        self.name = "bolus report"
        self.id_name = self.name.lower().replace(" ", "_")
        self.no_graph = True
        self.is_report = True

        table_stats.TableStats._register_stat(self)

    def do_plot(self, *args):
        START = 0
        DAYS = 5

        header = []

        ordered_vars, settings, setting_lists, variables, cfg = args

        for entry in common.Matrix.all_records(settings, setting_lists):
            break

        last_record_day = list(entry.results)[0]

        for i in range(START, START+DAYS):
            start_day = datetime.datetime.combine(
                last_record_day - datetime.timedelta(days=(i)),
                datetime.datetime.min.time()) # midnight morning

            end_day = start_day + datetime.timedelta(days=1)
            header += [html.H2(start_day.date())]
            header += Plot_and_Text(f"Bolus Study", set_config(dict(start=start_day, end=end_day), args))

        return None, header
