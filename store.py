import types, datetime
import yaml
import pathlib

import store
import store.simple
from store.simple import *

def inference_rewrite_settings(params_dict):
    if "run" in params_dict:
        params_dict["@run"] = params_dict["run"]
        del params_dict["run"]

    del params_dict["script"]

    if params_dict["framework"] == "tf":
        params_dict["framework"] = "TensorFlow"
    elif params_dict["framework"] == "onnxruntime":
        params_dict["framework"] = "Onnx Runtime"
    elif params_dict["framework"] == "pytorch":
        params_dict["framework"] = "PyTorch"

    return params_dict


def inference_parse_results(dirname, settings):
    results = types.SimpleNamespace()

    with open(pathlib.Path(dirname) / "stdout") as f:
        for line in f:
            if line.startswith("Mean latency:"):
                # eg: Mean latency: 29534116.227086924
                results.mean_latency = float(line.strip().rpartition(" ")[-1])

            if line.startswith("TestScenario.SingleStream"):
                # eg: TestScenario.SingleStream qps=33.83, mean=0.0295, time=600.155, queries=20305, tiles=50.0:0.0297,80.0:0.0300,90.0:0.0302,95.0:0.0303,99.0:0.0312,99.9:0.0329

                for kv in line.strip().partition(" ")[-1].split(", "):
                    k, v = kv.split("=")
                    try: v = float(v)
                    except ValueError: pass
                    results.__dict__[k] = v


    return [({}, results)]

store.custom_rewrite_settings = inference_rewrite_settings
store.simple.custom_parse_results = inference_parse_results
