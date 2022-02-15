#! /usr/bin/python

import json
import subprocess
import tempfile
import os
import glob

tmp = tempfile.mkstemp(dir="/tmp/")

cmd = [os.getenv("CMD_FROM_RUNNER")]
args_env = os.getenv("ARGS_FROM_RUNNER")

args = args_env.split(" ")

proc = subprocess.run(["echo"] + cmd + args,
                      cwd=tmp,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE)

runner_results = dict()
runner_results["exit_code"] = proc.returncode
runner_results["artifact_settings"] = " ".join(args)
runner_results["artifact_stdout"] = proc.stdout
runner_results["artifact_stderr"] = proc.stderr

for filepath in glob.glob(f"{tmp}/*"):
    with open(filepath) as f:
        content = "".join(f.readlines())

    runner_results["artifact_"filepath.rpartition("/")[-1]] = content
