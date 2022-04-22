import types, datetime
import yaml
from collections import defaultdict
import glob
import logging

import matrix_benchmarking.store as store
import matrix_benchmarking.store.simple as store_simple
import matrix_benchmarking.store.prom_db as store_prom_db
import matrix_benchmarking.parsing.prom as parsing_prom

INTERESTING_METRICS = [
    "DCGM_FI_DEV_POWER_USAGE",
    "DCGM_FI_DEV_FB_USED",
    "DCGM_FI_DEV_GPU_UTIL",
]

def _rewrite_settings(settings_dict):
    # add a @ on top of parameter name 'run'
    # to treat it as multiple identical executions

    #settings_dict["@run"] = settings_dict["run"]
    #del settings_dict["run"]

    settings_dict["ngpu"] = int(settings_dict.get("ngpu", 1))

    if settings_dict.get("mode"):
        if settings_dict.get("mode") == "training":
            settings_dict["inference_count"] = "0"
            settings_dict["inference_fraction"] = "0"
            settings_dict["training_count"] = "1"
            settings_dict["training_fraction"] = "1"
        else:
            settings_dict["inference_count"] = "1"
            settings_dict["inference_fraction"] = "1"
            settings_dict["training_count"] = "0"
            settings_dict["training_fraction"] = "0"

        settings_dict["partionner"] = "native"
        del settings_dict["mode"]

    try: del settings_dict["inference_time"]
    except KeyError: pass

    return settings_dict

def __parse_runai_gpu_burn(dirname, settings):
    results = types.SimpleNamespace()

    files = glob.glob(f"{dirname}/runai_gpu-burn*.log")
    log_filename = files[-1]
    if len(files) != 1:
        logging.warning(f"Found multiple log files in {dirname}. "
                        f"Taking the last one: '{log_filename}'.")

    speed = 0
    unit = ""
    with open(log_filename) as f:
        for line in f.readlines():
            if "proc'd" not in line: continue
            # 100.0%  proc'd: 27401 (3913 Gflop/s)   errors: 0   temps: 59 C
            speed = line.split()[3][1:]
            unit = line.split()[4][:1]

    results.speed = int(speed)
    results.unit = unit

    return results


def __parse_runai_ssd(dirname, settings):
    results = types.SimpleNamespace()
    results.oom =  defaultdict(lambda: False)
    results.runtime = {}
    results.training_speed = {}
    results.inference_speed = defaultdict(list)

    for fpath in glob.glob(f"{dirname}/*.log"):
        fname = fpath.rpartition("/")[-1]

        with open(fpath) as f:
            for line in f.readlines():
                if "Resource exhausted: OOM when allocating tensor" in line:
                    results.oom[fname] = True

                if line.startswith("Benchmark result:"):
                    results.inference_speed[fname].append(float(line.split()[-2])) # img/s
                if line.startswith("Single GPU mixed precision training performance"):
                    if line.strip()[-1] == ":":
                        store.simple.invalid_directory(dirname, settings, "no training result", warn=True)
                        return

                    results.training_speed[fname] = float(line.split()[-2]) # img/s

    if int(settings["inference_count"]) != len(results.inference_speed):
        store.simple.invalid_directory(dirname, settings, "no enough inference results", warn=True)
        return
    if int(settings["training_count"]) != len(results.training_speed):
        store.simple.invalid_directory(dirname, settings, "no enough training result", warn=True)
        return

    for fpath in glob.glob(f"{dirname}/pod_*.status.yaml"):
        fname = fpath.rpartition("/")[-1]
        if "inference" in fname:
            # inference jobs are interrupted, they don't have a runtime.
            continue

        with open(fpath) as f:
            try:
                pod = yaml.safe_load(f)
                state = pod["status"]["containerStatuses"][0]["state"]["terminated"]
                start = state["startedAt"]
                stop = state["finishedAt"]
                FMT = '%Y-%m-%dT%H:%M:%SZ'

                results.runtime[fname] = (datetime.datetime.strptime(stop, FMT) - datetime.datetime.strptime(start, FMT)).seconds

            except Exception as e:
                results.runtime[fname] = None

    return results


def _parse_results(fn_add_to_matrix, dirname, settings):
    model = settings.get("model")
    if not model:
        model = settings.get("benchmark")

    if not model:
        logging.error(f"Failed to parse '{dirname}', 'benchmark' setting not defined.")
        return

    MODEL_PARSE_FCTS = {
        "gpu-burn":  __parse_runai_gpu_burn,
        "ssd": __parse_runai_ssd,
    }

    try:
        parse_fct = MODEL_PARSE_FCTS[model]
    except KeyError:
        logging.error(f"Failed to parse '{dirname}', model={model} not recognized.")
        return

    results = parse_fct(dirname, settings)
    if results:
        fn_add_to_matrix(results)


# delegate the parsing to the simple_store
def parse_data():
    store.register_custom_rewrite_settings(_rewrite_settings)
    store_simple.register_custom_parse_results(_parse_results)

    return store_simple.parse_data()
