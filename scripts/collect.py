#!/usr/bin/env python3
"""collect.py OUT_DIR - Kyverno's PolicyReports, exactly as the cluster holds them.

Waits until Kyverno has reported on every workload tests.py started, for
every policy whose posture Kyverno reports (mapping/controls.yaml), then
writes them to OUT_DIR/raw/ unchanged. C2P's kyverno-cel plugin reads them
as they are: it takes each result's resource from the report's "scope"
when the result names none, and a result with no message gets C2P's own
"no message". The two changes this script made for C2P v2.0.0-rc.1, the
Go implementation, are gone with it (docs/decisions/0005).
"""
import json
import os
import subprocess
import sys
import time

from ruamel.yaml import YAML

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, ".cache", "run")
os.environ["KUBECONFIG"] = os.path.join(STATE, "kubeconfig")
WAIT_SECONDS = int(os.environ.get("REPORT_WAIT_SECONDS", "300"))


def kubectl_json(*args):
    p = subprocess.run(["kubectl", *args, "-o", "json"], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"kubectl {' '.join(args)}: {p.stderr.strip()}")
    return json.loads(p.stdout)


def reaches(rule, namespace):
    """Whether a policy's binding reaches pods in a namespace, for the workloads tests.py starts."""
    if rule in ("verify-models", "model-volumes", "models-need-kyverno"):
        return namespace == "inference"  # these match pods in namespaces for verified models only
    return True


def expected(tests_file, mapping):
    """(namespace, pod name prefix, policy) for every running workload and reported policy."""
    rules = [r for r, spec in mapping["rules"].items() if spec["posture"] == "kyverno"]
    want = []
    for w in json.load(open(tests_file))["workloads"]:
        if not w.get("running"):
            continue
        ns, kind, name = w["workload"].split("/")
        for r in rules:
            if reaches(r, ns):
                want.append((ns, name, r))
    return want


def reported(reports):
    seen = set()
    for rep in reports:
        scope = rep.get("scope") or {}
        for res in rep.get("results") or []:
            seen.add((scope.get("namespace"), scope.get("name", ""), res.get("policy")))
    return seen


def missing(want, seen):
    return [w for w in want if not any(ns == w[0] and name.startswith(w[1]) and pol == w[2]
                                       for ns, name, pol in seen)]


def main():
    out = sys.argv[1]
    mapping = YAML(typ="safe").load(open(os.path.join(ROOT, "mapping", "controls.yaml")))
    want = expected(os.path.join(STATE, "admission-tests.json"), mapping)
    deadline = time.time() + WAIT_SECONDS
    while True:
        polr = kubectl_json("get", "policyreports.wgpolicyk8s.io", "-A")
        gap = missing(want, reported(polr["items"]))
        if not gap or time.time() > deadline:
            break
        time.sleep(10)
    cpolr = kubectl_json("get", "clusterpolicyreports.wgpolicyk8s.io")
    os.makedirs(os.path.join(out, "raw"), exist_ok=True)
    json.dump(polr, open(os.path.join(out, "raw", "policyreports.json"), "w"), indent=2)
    json.dump(cpolr, open(os.path.join(out, "raw", "clusterpolicyreports.json"), "w"), indent=2)
    results = sum(len(r.get("results") or []) for r in polr["items"])
    print(f"== {len(polr['items'])} PolicyReports, {results} results"
          + (f"; still not reported after {WAIT_SECONDS}s: {gap}" if gap else "; every running workload reported for every policy"))


if __name__ == "__main__":
    main()
