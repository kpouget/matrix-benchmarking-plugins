from collections import defaultdict
import statistics as stats
import datetime

import plotly.graph_objs as go

import matrix_view.table_stats
from common import Matrix
from matrix_view import COLORS

def register():
    Plot("Mean latency")
    Plot("QPS")

class Plot():
    def __init__(self, name):
        self.name = name
        self.id_name = name

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, params, param_lists, variables, cfg):
        fig = go.Figure()

        XY = defaultdict(dict)
        XYerr = defaultdict(dict)

        if self.name == "QPS":
            y_key = lambda results: results.qps
        elif self.name == "Mean latency":
            y_key = lambda results: results.mean_latency

        x_variable_key = ordered_vars[0]
        x_key = lambda entry: entry.params.__dict__[x_variable_key]

        is_gathered = False
        for entry in Matrix.all_records(params, param_lists):
            legend_name = " ".join([f"{key}={entry.params.__dict__[key]}" for key in variables if key != x_variable_key])

            if entry.is_gathered:
                is_gathered = True

                y_values = [y_key(entry.results) for entry in entry.results]

                y = stats.mean(y_values)
                y_err = stats.stdev(y_values) if len(y_values) > 2 else 0

                legend_name += " " + " ".join(entry.gathered_keys.keys()) + f" x{len(entry.results)}"

                XYerr[legend_name][x_key(entry)] = y_err

            else:
                y = y_key(entry.results)

                gather_key_name = [k for k in entry.params.__dict__.keys() if k.startswith("@")][0]

            XY[legend_name][x_key(entry)] = y

        y_max = 0

        data = []
        for legend_name in XY:
            x = list(sorted(XY[legend_name].keys()))
            y = list([XY[legend_name][_x] for _x in x])

            y_max = max(y + [y_max])

            color = COLORS(list(XY.keys()).index(legend_name))

            error_y = dict(type='data', array=list(XYerr[legend_name].values())) if XYerr else None

            data.append(go.Bar(name=legend_name,
                               x=x, y=y,
                               marker_color=color,
                               hoverlabel= {'namelength' :-1},
                               legendgroup=legend_name,
                               error_y=error_y,
                               ))


        fig = go.Figure(data=data)
        log_scale = cfg.get("log-scale", False) == "y"

        if log_scale:
            fig.update_xaxes(type="log")
            fig.update_yaxes(type="log")
            import math
            # https://plotly.com/python/reference/layout/yaxis/#layout-yaxis-range
            y_max = math.log(y_max, 10)


        if self.name == "QPS":
            fig.update_layout(title="QPS", title_x=0.5,
                              showlegend=True,
                              xaxis_title=x_variable_key + (" [log scale]" if log_scale else ""),
                              yaxis_title=self.name + " (in ..., lower is better)" + (" [log scale]" if log_scale else ""),
                              )
        elif self.name == "Mean latency":
            fig.update_layout(title="Mean latency", title_x=0.5,
                              showlegend=True,
                              xaxis_title=x_variable_key + (" [log scale]" if log_scale else ""),
                              yaxis_title=self.name + " (in ..., lower is better)" + (" [log scale]" if log_scale else ""),
                              )


        return fig, ""
