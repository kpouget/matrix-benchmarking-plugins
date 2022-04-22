from collections import defaultdict
import statistics as stats
import datetime
import logging

import plotly.graph_objs as go
import plotly.subplots

import matrix_benchmarking.common as common
import matrix_benchmarking.plotting.table_stats as table_stats
from .. import store as runai_store

def register():
    ComparisonPlot()
    ComparisonPlot(metric_name="GPU Power Usage", yaxis_title="Watt", y_units="Watt")
    ComparisonPlot(metric_name="GPU Compute Usage", yaxis_title="% of the GPU", y_units="%")
    ComparisonPlot(metric_name="GPU Memory Usage", yaxis_title="% of the memory", y_units="GB")

    PromPlot("DCGM_FI_DEV_POWER_USAGE", "Power usage",
             filter_x=runai_store.filter_runai_metrics)
    PromPlot("DCGM_FI_DEV_FB_USED", "Memory usage (in GB)",
             filter_x=runai_store.filter_runai_metrics,
             transform_y=lambda y:y/1000)
    PromPlot("DCGM_FI_DEV_GPU_UTIL", "Compute usage (in %)",
             filter_x=runai_store.filter_runai_metrics)

def entry_name(entry, variables):
    for key in ["inference_count", "inference_fraction",
                "training_count", "training_fraction",
                "expe", "partionner"]:
        try: variables.pop(key)
        except KeyError: pass

    inference_part = f"{entry.settings.inference_count} x inference at {int(float(entry.settings.inference_fraction)*100)}%"
    training_part = f"{entry.settings.training_count} x training at {int(float(entry.settings.training_fraction)*100)}%"

    if not entry.results.training_speed:
        name = inference_part
    elif not entry.results.inference_speed:
        name = training_part
    else:
        name = f"{inference_part}<br>{training_part}"

    name += f"<br>{1/entry.results.group_slice*100:.0f}% of the GPU/Pod"

    if entry.settings.partionner == "sequential":
        if int(entry.settings.inference_count) > 1 or  int(entry.settings.training_count) > 1:
            name += "<br>(sequential)"

    if variables:
        remaining_args = "<br>".join([f"{key}={entry.settings.__dict__[key]}" for key in variables])
        name += "<br>" + remaining_args

    if entry.settings.partionner == "sequential":
        if entry.results.training_speed:
            if entry.settings.training_count == "1":
                name += "<br>(<b>training reference</b>)"
        else:
            if entry.settings.inference_count == "1":
                name += "<br>(<b>inference reference</b>)"
    return name

class ComparisonPlot():
    def __init__(self, metric_name=None, yaxis_title=None, y_units="img/s"):
        if metric_name:
            self.name = metric_name
            self.metric_key = metric_name.replace(" ", "_").lower()
            self.id_name = "metric" + self.metric_key
        else:
            self.name = f"Compute speed"
            self.id_name = f"compute_spee"
            self.metric_key = None

        self.yaxis_title = yaxis_title
        self.y_units = y_units
        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, param_lists, variables, cfg):
        legend_names = set()
        results = defaultdict(dict)
        group_names = []
        group_slices = dict()
        group_lengths = defaultdict(int)

        group_legends = defaultdict(list)

        slices = [1]
        ref_groups = set()
        ref_values = dict(training=None, inference=None)
        max_values = dict(training=0, inference=0)
        ref_keys = {}

        for entry in common.Matrix.all_records(settings, param_lists):
            full_gpu = settings['partionner'] == "sequential"

            group_name = entry_name(entry, variables)
            group_names.append(group_name)

            group_slices[group_name] = entry.results.group_slice
            slices.append(entry.results.group_slice)

            if self.metric_key is None:
                mode_values = dict(inference=entry.results.inference_speed, training=entry.results.training_speed)
            else:
                mode_values = dict(metric={1: entry.results.__dict__[self.metric_key]})

            for mode_name, mode_data in mode_values.items():
                for idx, values in enumerate(mode_data.values()):
                    group_lengths[group_name] += 1

                    if mode_name == "metric":
                        legend_name = ""
                        value = values
                    elif mode_name == "inference":
                        legend_name = f"Inference #{idx}"
                        value = sum(values)/len(values)
                        max_values["inference"] = max([max_values["inference"], value])
                    else:
                        legend_name = f"Training #{idx}"
                        value = values
                        max_values["training"] = max([max_values["training"], value])

                    if full_gpu:
                        legend_name += " (full)"

                    ref_keys[legend_name] = mode_name
                    legend_names.add(legend_name)
                    results[legend_name][group_name] = value
                    group_legends[group_name].append(legend_name)

            if settings["partionner"] == "sequential":
                for key in ref_values:
                    if entry.settings.__dict__[f"{key}_count"] == "1":
                        if ref_values[key] is not None:
                            logging.warning(f"Found multiple {key} reference values (prev: {ref_values[key]}), new: {value} ...")

                        ref_values[key] = value
                        ref_groups.add(group_name)

        fig = plotly.subplots.make_subplots(specs=[[{"secondary_y": True}]])
        x_labels = []
        max_extra_ref_pct = 0
        for legend_name in sorted(legend_names):
            x_labels = []
            x_idx = []
            y_base = []
            y_extra = []
            text_base = []
            text_extra = []

            def sort_key(group_name):
                sort_index = 0

                if "x inference" not in group_name:
                    sort_index += 100
                    #if "1 x training" in group_name: sort_index += 50
                if "training at 100%" in group_name:
                    sort_index += 50

                return f"{sort_index:04d} {group_name}"

            group_names.sort(key=sort_key)

            width = 10/(max(map(len, group_legends.values())))

            for group_idx, group_name in enumerate(group_names):
                x_labels.append(group_name)

                group_length = group_lengths[group_name]

                try: legend_idx = group_legends[group_name].index(legend_name)
                except ValueError: legend_idx = 0


                position = group_idx*10 - (group_length/2)*width + legend_idx*width + 1/2*width

                x_idx.append(position)

                try: value = results[legend_name][group_name]
                except KeyError:
                    print("missing", legend_name, group_name)
                    value = None

                if value is None or group_name in ref_groups:
                    if group_name in ref_groups:
                        if self.metric_key:
                            what = "Inference" if "inference reference" in group_name else "Training"
                            text_base.append(f"{what} reference<br>{value or -1:.0f} {self.y_units}")
                        else:
                            text_base.append(f"{ref_keys[legend_name].title()} reference: {value or -1:.0f} {self.y_units}")
                        y_base.append(value)
                    else:
                        text_base.append(None)
                        y_base.append(None)

                    text_extra.append(None)
                    y_extra.append(None)
                else:
                    slices = group_slices[group_name]
                    ref = ref_values.get(ref_keys[legend_name])
                    if ref is None:
                        if not self.metric_key:
                            logging.warning(f"No ref found for {legend_name}")
                        ref = value*group_slices[group_name]
                        if ref == 0: ref = 1
                    local_ref = ref/slices
                    text_base.append(f"{value:.1f} {self.y_units}")
                    base = ref/group_slices[group_name]
                    extra = value-base
                    pct = (value-local_ref)/local_ref*100
                    text_extra.append(f"{pct:+.1f}%")
                    if pct >= 1:
                        y_base.append(base)
                        y_extra.append(extra)
                    else:
                        y_base.append(value)
                        y_extra.append(0.001 if abs(pct) > 0.5 else 0)

                    max_extra_ref_pct = max([max_extra_ref_pct, pct])

            is_training = ref_keys[legend_name] == "training"
            secondary_axis = is_training

            name = "Training" if is_training else "Inference"
            if "full" in legend_name:
                color = "cornflowerblue" if is_training else "green"
                name = f"Full GPU {name}"
            else:
                color = "mediumslateblue" if is_training else "darkgreen"
                name = f"Fractional {name}"


            show_legend = "#0" in legend_name

            fig.add_trace(
                go.Bar(name=name, marker_color=color,
                       x=x_idx, y=y_base, text=text_base,
                       width=width-(width*0.1),
                       showlegend=show_legend,
                       legendgroup=name,
                       hoverlabel= {'namelength' :-1}),
                secondary_y=secondary_axis,
            )

            if self.metric_key: continue

            fig.add_trace(
                go.Bar(name=name, marker_color=color,
                       x=x_idx, y=y_extra, text=text_extra,
                       marker_line_color="indianred", marker_line_width=2,
                       width=width-(width*0.1),
                       legendgroup=name,
                       showlegend=False,
                       hoverlabel= {'namelength' :-1}),
                secondary_y=secondary_axis,
            )

        fig.update_xaxes(
            tickvals=[10*i for i in range(len(x_labels))],
            ticktext=x_labels
        )

        if ref_keys:
            ref = ref_values.get(list(ref_keys.values())[0])
            for slices in [1, 2, 3, 4, 6] if ref else []:

                fig.add_trace(go.Scatter(
                    x=[x_idx[0]-5, x_idx[-1]],
                    y=[ref*1/slices, ref*1/slices],
                    showlegend=False,
                    mode="lines+text",
                    text=[f"100%<br>of the<br>reference<br>speed" if slices == 1 else f"{1/slices*100:.0f}%"],
                    textposition="bottom center",
                    line=dict(
                        color="gray",
                        width=1,
                        dash='dashdot',
                    ),
                ), secondary_y=True)

        if self.metric_key:
            fig.update_layout(title=self.name,
                              title_x=0.5,
                              showlegend=False,
                              yaxis_title=self.yaxis_title,
                              )
        else:
            yaxis_title = "<b>{what} speed</b> (in img/s, higher is better)"

            fig.update_layout(title=f"NVDIA Deep Learning SSD AI/ML Processing Speed Comparison<br>using Run:AI GPU fractional GPU",
                              showlegend=True,
                              yaxis_title=yaxis_title.format(what="Inference"),
                              )

            fig.update_yaxes(title_text=yaxis_title.format(what="Training"), secondary_y=True)
        fig.update_layout(barmode='stack',
                          title_x=0.5,
                          #paper_bgcolor='rgb(248, 248, 255)',
                          plot_bgcolor='rgb(248, 248, 255)',
                          )


        fig.update_yaxes(showgrid=False, showline=True, linewidth=0.1, linecolor='black')
        fig.update_xaxes(showgrid=False, showline=True, linewidth=0.1, linecolor='black', mirror=True)


        if not self.metric_key:
            training_better_than_ref = (max_values["training"] - ref_values["training"])/ref_values["training"]
            inference_better_than_ref = (max_values["inference"] - ref_values["inference"])/ref_values["inference"]

            fig.update_yaxes(range=[0, max_values["inference"] * (1.02+training_better_than_ref)], secondary_y=False)
            fig.update_yaxes(range=[0, max_values["training"] * (1.02+inference_better_than_ref)], secondary_y=True)

        return fig, ""

class PromPlot():
    def __init__(self, metric, y_title, filter_x=lambda x:x, transform_y=lambda x:x):
        self.name = f"Prom: {metric}"
        self.id_name = f"prom_overview_{metric}"
        self.metric = metric
        self.y_title = y_title
        self.filter_x = filter_x
        self.transform_y = transform_y

        table_stats.TableStats._register_stat(self)
        common.Matrix.settings["stats"].add(self.name)

    def do_hover(self, meta_value, variables, figure, data, click_info):
        return "nothing"

    def do_plot(self, ordered_vars, settings, param_lists, variables, cfg):
        fig = go.Figure()

        plot_title = f"Prometheus: {self.metric}"
        y_max = 0
        for entry in common.Matrix.all_records(settings, param_lists):
            for metric in self.filter_x(entry.results.metrics[self.metric]):
                x_values = [x for x, y in metric["values"]]
                y_values = [self.transform_y(float(y)) for x, y in metric["values"]]

                name_key = entry_name(entry, variables).replace("<br>", " - ").replace("<b>", "").replace("</b>", "")

                x_start = x_values[0]
                x_values = [(x-x_start)/60 for x in x_values]

                y_max = max([y_max]+y_values)

                trace = go.Scatter(x=x_values, y=y_values,
                                   name=name_key,
                                   hoverlabel= {'namelength' :-1},
                                   showlegend=True,
                                   mode='markers+lines')
                fig.add_trace(trace)

        fig.update_layout(
            title=plot_title, title_x=0.5,
            yaxis=dict(title=self.y_title, range=[0, y_max*1.05]),
            xaxis=dict(title=f"Time (in min)"))

        fig.update_layout(legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ))

        return fig, ""
