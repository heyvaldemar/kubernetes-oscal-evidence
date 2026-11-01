#!/usr/bin/env python3
"""collect.py OUT_DIR - Kyverno's PolicyReports, as they are and as C2P can read them.

Waits until Kyverno has reported on every workload tests.py started, for
every policy whose posture Kyverno reports (mapping/controls.yaml), then
writes:

  OUT_DIR/raw/   the reports exactly as the cluster holds them
  OUT_DIR/c2p/   the files C2P's Kyverno plugin reads, by the names it reads

Two changes between the two, and only these, each because C2P's Kyverno
plugin (v2.0.0-rc.1) cannot read Kyverno 1.19's reports as they are:

1. Kyverno writes one report per resource and names the resource once, in
   the report's "scope", leaving each result's "resources" empty. The plugin
   reads the resource from each result's "resources", so from Kyverno's own
   reports it makes observations with no subjects, and C2P then calls every
   control not satisfied, whatever the results say. Here each result with no
   "resources" gets the report's scope as its one resource.
2. Kyverno gives a passing result no message. The plugin copies the message
   into each subject's "reason", C2P's own schema check refuses an empty
   property value, and c2pcli exits 1 having written nothing. Here a result
   with no message gets one that says so: "pass; Kyverno gave no message".

Nothing else is touched, and the test suite holds that to be so.
"""
import copy
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


def scoped(report):
    """A report as C2P can read it: the two changes the docstring names, and no other."""
    out = copy.deepcopy(report)
    scope = out.get("scope")
    for result in out.get("results") or []:
        if not result.get("resources") and scope:
            result["resources"] = [scope]
        if not (result.get("message") or "").strip():
            result["message"] = f"{result.get('result', 'no result')}; Kyverno gave no message"
    return out


def expected(tests_file, mapping):
    """(namespace, pod name prefix, policy) for every running workload and reported policy."""
    rules = [r for r, spec in mapping["rules"].items() if spec["posture"] == "kyverno"]
    want = []
    for w in json.load(open(tests_file))["workloads"]:
        if not w.get("running"):
            continue
        ns, kind, name = w["workload"].split("/")
        for r in rules:
            if r in ("verify-models", "model-volumes", "models-need-kyverno") and ns != "inference":
                continue  # these match pods in namespaces for verified models only
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
    for d in ("raw", "c2p"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    json.dump(polr, open(os.path.join(out, "raw", "policyreports.json"), "w"), indent=2)
    json.dump(cpolr, open(os.path.join(out, "raw", "clusterpolicyreports.json"), "w"), indent=2)
    empty = {"apiVersion": "v1", "kind": "List", "items": []}
    c2p = os.path.join(out, "c2p")
    json.dump({**polr, "items": [scoped(r) for r in polr["items"]]},
              open(os.path.join(c2p, "policyreports.wgpolicyk8s.io.yaml"), "w"), indent=2)
    json.dump({**cpolr, "items": [scoped(r) for r in cpolr["items"]]},
              open(os.path.join(c2p, "clusterpolicyreports.wgpolicyk8s.io.yaml"), "w"), indent=2)
    # The plugin also reads Kyverno's legacy policy lists; the flagship has none.
    json.dump(empty, open(os.path.join(c2p, "policies.kyverno.io.yaml"), "w"))
    json.dump(empty, open(os.path.join(c2p, "clusterpolicies.kyverno.io.yaml"), "w"))
    results = sum(len(r.get("results") or []) for r in polr["items"])
    print(f"== {len(polr['items'])} PolicyReports, {results} results"
          + (f"; still not reported after {WAIT_SECONDS}s: {gap}" if gap else "; every running workload reported for every policy"))


if __name__ == "__main__":
    main()
