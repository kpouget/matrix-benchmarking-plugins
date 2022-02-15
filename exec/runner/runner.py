#! /usr/bin/python

import json
import subprocess
import tempfile
import os, sys
import glob
import types

tmp = tempfile.mkdtemp()

cmd = [os.getenv("CMD_FROM_RUNNER")]
args_env = os.getenv("ARGS_FROM_RUNNER")

args = args_env.split(" ")

proc = subprocess.run(cmd + args,
                      cwd=tmp,
                      stdin=subprocess.PIPE,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE)

runner_results = dict()
runner_results["exit_code"] = proc.returncode
runner_results["artifact_settings"] = " ".join(args)
runner_results["artifact_stdout"] = proc.stdout.decode("utf8")
runner_results["artifact_stderr"] = proc.stderr.decode("utf8")

for filepath in glob.glob(f"{tmp}/*"):
    with open(filepath) as f:
        content = "".join(f.readlines())

    runner_results["artifact_"+filepath.rpartition("/")[-1]] = content


def __parse_osu(dirname):
    results = types.SimpleNamespace()

    results.osu_title = None
    results.osu_legend = None
    results.measures = {}

    with open(f"{dirname}/mpijob.launcher.log") as f:
        for _line in f:

            current_results = types.SimpleNamespace()

            line = _line.strip()
            if line == "TIMEOUT": break
            if not line: continue
            if "Failed to add the host" in line: continue
            if "Warning: Permanently added" in line: continue

            if line.startswith('#'):
                if results.osu_title is None:
                    results.osu_title = line[1:].strip()
                elif results.osu_legend is None:
                    results.osu_legend = line[1:].strip().split(maxsplit=1)
                else:
                    raise ValueError("Found too many comments ...")

                continue
            try:
                size, bw = line.strip().split()
                results.measures[int(size)] = float(bw)
            except ValueError as e:
                print(f"ERROR: Failed to parse the Launcher logs in {f.name}: {e}")
                print(line.strip())

    return results

res = __parse_osu(tmp)

for k, v in res.__dict__.items():
    runner_results[f"data_{k}"] = v

print(json.dumps(runner_results, indent = 4) )
sys.exit(proc.returncode)
