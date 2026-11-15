#!/usr/bin/env python3
"""evidence.py OUT_DIR - OSCAL assessment results for one run, one file per framework.

1. C2P 1.0.0 (scripts/c2p.py, in C2P's own environment) turns the component
   definition, Kyverno's PolicyReports and the API server's answers to the
   dry run (scripts/tests.py --dry-run) into one assessment results for
   both engines, and a control-level posture over it. Both are kept as C2P
   wrote them, in OUT_DIR/c2p/.
2. For each framework in mapping/controls.yaml, the results are completed
   with compliance-trestle's OSCAL models into
   OUT_DIR/assessment-results-<framework>.json:
   - C2P's observations for the policies the framework's controls rest on,
     unchanged: what each engine said about each pod running in the
     cluster, check by check, and every observation names its check, so
     its engine;
   - one observation per admission test the framework's controls name: the
     planted pod, what the flagship expects, and what the API server said;
   - one finding per mapped control, with its catalog statement id and a
     state. C2P 1.0.0 writes no findings, so the findings are written here,
     and a control is "satisfied" only when all of these hold:
       a. C2P's posture calls it satisfied;
       b. every check the component definition declares for every policy
          that carries it reported at least one pod, and every result is a
          pass: Kyverno's report, and for a policy marked dry_run, the API
          server's dry run as well. C2P's posture calls a control satisfied
          while one of its expected checks reported nothing, and says so
          only in its coverage; here that control is not satisfied;
       c. every test that proves it did what mapping/controls.yaml says:
          refused by the named policy, with the flagship's expected words,
          or admitted.
     Anything else is "not-satisfied", and the finding says why. A control
     C2P does not call satisfied can never be called satisfied here.
   Each document imports an assessment plan written beside it,
   OUT_DIR/assessment-plan-<framework>.json: C2P 1.0.0 writes none.
3. Every document is read back by trestle's models before it is written,
   and OUT_DIR/summary.md says what the run showed, control by control.

Exits 2 if C2P fails or a document does not parse: no evidence is a
failure, never a pass. Judging the results is scripts/gate.py's work.
"""
import copy
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid

from ruamel.yaml import YAML
from trestle.oscal.assessment_results import AssessmentResults
from trestle.oscal.assessment_plan import AssessmentPlan

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, ".cache", "run")
FLAGSHIP_LOCK = os.path.join(ROOT, "flagship.lock")
TRESTLE_NS = "https://oscal-compass.github.io/compliance-trestle/schemas/oscal"
OUR_NS = "https://github.com/heyvaldemar/kubernetes-oscal-evidence/ns"
SEED = uuid.UUID("9a3f0c6e-2b1d-4c8e-8f5a-7d2e1b0c4a99")


def env(name, default=""):
    return os.environ.get(name, default)


def statement_ids(catalog):
    out = {}

    def walk(controls):
        for c in controls or []:
            out[c["id"]] = next((p["id"] for p in c.get("parts", [])
                                 if p.get("name") == "statement" and p.get("id")), c["id"])
            walk(c.get("controls"))

    def groups(gs):
        for g in gs or []:
            walk(g.get("controls"))
            groups(g.get("groups"))

    cat = json.load(open(catalog))["catalog"]
    groups(cat.get("groups"))
    walk(cat.get("controls"))
    return out


def prop(name, value, ns=OUR_NS):
    return {"name": name, "ns": ns, "value": str(value)}


def c2p_prop(props, name):
    """A prop C2P wrote. C2P 1.0.0 writes its props with no namespace; v2.0.0-rc.1, the Go
    implementation, wrote them in trestle's. Never one of this repository's own."""
    return next((p["value"] for p in props or []
                 if p["name"] == name and p.get("ns", TRESTLE_NS).startswith(TRESTLE_NS)), None)


ENGINES = {"kyverno": "Kyverno", "dry_run": "the API server's dry run"}


def checks_of(name, rule):
    """(engine, check id) for every check the component definition declares for a policy."""
    out = []
    if rule["posture"] == "kyverno":
        out.append((ENGINES["kyverno"], name))
    if rule.get("dry_run"):
        out.append((ENGINES["dry_run"], f"vap-{name}"))
    return out


def run_c2p(cd, reports, dry_run, c2p_dir):
    """C2P's assessment results for both engines, and its posture, written as C2P writes them."""
    os.makedirs(c2p_dir, exist_ok=True)
    python = env("C2P_PYTHON", os.path.join(ROOT, ".cache", "c2p", "bin", "python"))
    cmd = [python, "-I", os.path.join(ROOT, "scripts", "c2p.py"), cd, reports, dry_run, c2p_dir]
    p = subprocess.run(cmd, capture_output=True, text=True)
    with open(os.path.join(c2p_dir, "c2p.log"), "w") as log:
        log.write(f"$ {' '.join(cmd)}\n{p.stdout}{p.stderr}\n")
    if p.returncode != 0:
        print(f"C2P failed; see c2p/c2p.log: {(p.stderr.strip().splitlines() or ['no message'])[-1]}", file=sys.stderr)
        sys.exit(2)
    print(p.stdout.strip())
    posture = {}
    for comp in json.load(open(os.path.join(c2p_dir, "posture.json"))).get("components", []):
        for c in comp.get("controls", []):
            posture[c["controlId"]] = {"state": c["state"], "remarks": c.get("remarks", ""),
                                       "assessed": c["coverage"]["assessedChecks"],
                                       "expected": c["coverage"]["expectedChecks"]}
    return json.load(open(os.path.join(c2p_dir, "assessment-results.json"))), posture


def assessment_plan(fw, spec, controls, flagship, now):
    """The plan each framework's results import: the controls reviewed, against the
    component definition. C2P 1.0.0 writes no assessment plan."""
    return {"assessment-plan": {
        "uuid": str(uuid.uuid5(SEED, f"{env('RUN_ID', 'local')}/plan/{fw}")),
        "metadata": {"title": f"Admission controls of {flagship[0].split('/')[1]} {flagship[1]}: "
                              f"{spec['title']}, the plan",
                     "last-modified": now, "version": env("EVIDENCE_VERSION", "unreleased"),
                     "oscal-version": "1.1.3"},
        "import-ssp": {"href": "component-definition.json",
                       "remarks": ("There is no system security plan: the run assesses the flagship's admission "
                                   "policies as the component definition beside this plan describes them.")},
        "reviewed-controls": {"control-selections": [
            {"include-controls": [{"control-id": c["control"]} for c in controls]}]},
    }}


def judge_test(name, spec, recorded):
    """(passed, why) for one admission test, against what the mapping says it must show."""
    t = recorded.get(name)
    if t is None:
        return False, "the run recorded no such test"
    if spec["outcome"] == "admitted":
        return (True, "admitted") if t["admitted"] else (False, f"refused by {t['refused_by']}: {t['message']}")
    if t["admitted"]:
        return False, "admitted; it must be refused"
    if t["refused_by"] not in spec["by"]:
        return False, f"refused by {t['refused_by']}, not by {' or '.join(spec['by'])}: {t['message']}"
    if t["expect"] and t["expect"] not in t["message"]:
        return False, f"refused by {t['refused_by']}, without the expected words '{t['expect']}': {t['message']}"
    return True, f"refused by {t['refused_by']}: {t['message']}"


def decide(control, rules, posture, by_check, tests):
    """Why a control is not satisfied, as a list (empty when it is), and the observations
    it rests on: C2P's posture, every engine's checks for its policies, and its tests."""
    reasons, related = [], []
    c2p = posture.get(control["control"])
    if c2p is None:
        reasons.append("C2P's posture has no row for it")
    elif c2p["state"] != "satisfied":
        reasons.append(f"C2P's posture: {c2p['state']} ({c2p['remarks']})")
    for r in control["rules"]:
        for engine, check in checks_of(r, rules[r]):
            obs = by_check.get(check, [])
            related += [o["uuid"] for o in obs]
            subjects = [s for o in obs for s in o.get("subjects") or []]
            if not subjects:
                reasons.append(f"{engine} reported no running pod for {r}")
            bad = [s["title"] for s in subjects if c2p_prop(s.get("props"), "result") != "pass"]
            if bad:
                reasons.append(f"{r} did not pass in {engine} for {len(bad)} pod(s): {'; '.join(bad)}")
    for t in control["proven_by"]:
        if not tests[t][0]:
            reasons.append(f"test {t}: {tests[t][1]}")
    return reasons, related


def test_observation(name, spec, t, passed, why, rules, collected, flagship):
    repo, tag = flagship
    source = (t or {}).get("source", "")
    obs = {
        "uuid": str(uuid.uuid5(SEED, f"{env('RUN_ID', 'local')}/test/{name}")),
        "title": f"Admission test: {name}",
        "description": (t or {}).get("flagship_says") or name,
        "methods": ["TEST"],
        "props": [prop("test", name), prop("expected-outcome", spec["outcome"]),
                  prop("verdict", "pass" if passed else "fail")]
                 + [prop("refused-by-expected", r) for r in spec.get("by", [])]
                 + [{"name": "assessment-rule-id", "value": r} for r in rules],
        "collected": collected,
        "remarks": why,
    }
    if t is not None:
        obs["props"].append(prop("admitted", "true" if t["admitted"] else "false"))
        if t.get("refused_by"):
            obs["props"].append(prop("refused-by", t["refused_by"]))
        if t.get("expect"):
            obs["props"].append(prop("expected-words", t["expect"]))
    if source.startswith("tests/"):
        obs["relevant-evidence"] = [{"href": f"https://github.com/{repo}/blob/{tag}/{source}",
                                     "description": f"The planted pod, as the flagship ships it at {tag}"}]
    return obs


def main():
    out = os.path.abspath(sys.argv[1])
    mapping_path = os.path.abspath(env("MAPPING", os.path.join(ROOT, "mapping", "controls.yaml")))
    cd = os.path.abspath(env("COMPONENT_DEFINITION", os.path.join(ROOT, "oscal", "component-definition.json")))
    reports = os.path.abspath(env("REPORTS", os.path.join(STATE, "reports", "raw")))
    dry_run = os.path.abspath(env("DRY_RUN", os.path.join(STATE, "dry-run.json")))
    tests_file = os.path.abspath(env("ADMISSION_TESTS", os.path.join(STATE, "admission-tests.json")))
    m = YAML(typ="safe").load(open(mapping_path))
    run = json.load(open(tests_file))
    recorded = {t["test"]: t for t in run["tests"]}
    line = next(l for l in open(FLAGSHIP_LOCK) if l.strip() and not l.startswith("#")).split()
    flagship = (line[0], line[1])
    catalogs = {l.split()[0]: l.split()[1] for l in open(os.path.join(ROOT, "catalogs.lock"))
                if l.strip() and not l.startswith("#")}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    run_url = (f"{env('GITHUB_SERVER_URL')}/{env('GITHUB_REPOSITORY')}/actions/runs/{env('GITHUB_RUN_ID')}"
               if env("GITHUB_RUN_ID") else "a local run")
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(cd, os.path.join(out, "component-definition.json"))

    unmapped = sorted(set(recorded) - set(m["tests"]))
    tests = {name: judge_test(name, spec, recorded) for name, spec in m["tests"].items()}
    for name in unmapped:
        tests[name] = (False, "recorded by the run but not named in mapping/controls.yaml")

    c2p_ar, posture = run_c2p(cd, reports, dry_run, os.path.join(out, "c2p"))
    c2p_obs = c2p_ar["assessment-results"]["results"][0].get("observations") or []
    verdict = {"run": run_url, "plant": run.get("plant"), "flagship": f"{flagship[0]} {flagship[1]}",
               "frameworks": {}, "tests": {k: {"passed": v[0], "why": v[1]} for k, v in tests.items()},
               "unmapped_tests": unmapped, "workloads": run["workloads"]}
    for fw, spec in m["frameworks"].items():
        controls = [c for c in m["controls"] if c["framework"] == fw]
        fw_rules = {r for c in controls for r in c["rules"]}
        plan_path = os.path.join(out, f"assessment-plan-{fw}.json")
        with open(plan_path, "w") as f:
            json.dump(assessment_plan(fw, spec, controls, flagship, now), f, indent=2, ensure_ascii=False)
            f.write("\n")
        try:
            AssessmentPlan.oscal_read(pathlib.Path(plan_path))
        except Exception as e:
            print(f"{plan_path} does not parse as an OSCAL assessment plan: {e}", file=sys.stderr)
            sys.exit(2)
        ar = copy.deepcopy(c2p_ar)
        res = ar["assessment-results"]["results"][0]
        by_check = {}
        observations = []
        for o in c2p_obs:
            if c2p_prop(o.get("props"), "assessment-rule-id") in fw_rules:
                observations.append(o)
                by_check.setdefault(c2p_prop(o.get("props"), "assessment-check-id"), []).append(o)
        smt = statement_ids(os.path.join(ROOT, ".cache", "catalogs", spec["catalog"]))

        test_obs = {}
        for c in controls:
            for t in c["proven_by"]:
                if t not in test_obs:
                    passed, why = tests[t]
                    rules = sorted({r for cc in controls if t in cc["proven_by"] for r in cc["rules"]})
                    test_obs[t] = test_observation(t, m["tests"][t], recorded.get(t), passed, why, rules, now, flagship)
        observations += list(test_obs.values())

        findings, states = [], {}
        for c in controls:
            reasons, related = decide(c, m["rules"], posture, by_check, tests)
            related += [test_obs[t]["uuid"] for t in c["proven_by"]]
            state = "not-satisfied" if reasons else "satisfied"
            states[c["control"]] = {"state": state, "why": reasons}
            engines = sorted({e for r in c["rules"] for e, _ in checks_of(r, m["rules"][r])})
            c2p = posture.get(c["control"])
            findings.append({
                "uuid": str(uuid.uuid5(SEED, f"{env('RUN_ID', 'local')}/{fw}/{c['control']}")),
                "title": f"{c['control']}: {state}",
                "description": ("; ".join(reasons) if reasons else
                                (f"{' and '.join(engines)} reported every running pod passing "
                                 + ", ".join(r for r in c["rules"] if checks_of(r, m["rules"][r])) + ", and "
                                 if engines else "")
                                + f"every test that proves it did what the mapping says ({', '.join(c['proven_by'])})."),
                "props": [prop("control", c["control"]), prop("judged-by", "scripts/evidence.py")]
                         + [prop("matrix-row", r) for r in c.get("matrix", [])]
                         + [prop("engine", e) for e in engines] + [
                          prop("c2p-posture", f"{c2p['state']}, {c2p['assessed']} of {c2p['expected']} expected checks "
                                              "reported" if c2p else "no row")],
                "target": {"type": "statement-id", "target-id": smt[c["control"]],
                           "status": {"state": state, "reason": "pass" if state == "satisfied" else "fail"}},
                "related-observations": [{"observation-uuid": u} for u in related],
            })
        verdict["frameworks"][fw] = states

        doc = ar["assessment-results"]
        doc["metadata"] = {
            "title": f"Admission controls of {flagship[0].split('/')[1]} {flagship[1]}: {spec['title']}, one run",
            "last-modified": now, "version": env("EVIDENCE_VERSION", "unreleased"),
            "oscal-version": doc["metadata"].get("oscal-version", "1.1.3"),
            "props": [prop("run", run_url), prop("commit", env("GITHUB_SHA", "local")),
                      prop("flagship", f"{flagship[0]}@{flagship[1]}"),
                      prop("catalog", catalogs[spec["catalog"]]),
                      prop("plant", run.get("plant") or "none")],
            "remarks": ("Observations of Kyverno's PolicyReports and of the API server's dry run are C2P's, "
                        "unchanged; each names its check, and so its engine. Admission test observations and "
                        "every finding are written by scripts/evidence.py; c2p/ holds C2P's own results for "
                        "both engines and its posture."),
        }
        doc["import-ap"] = {"href": f"assessment-plan-{fw}.json"}
        res["title"] = f"{spec['title']}: the admission controls of {flagship[0].split('/')[1]} {flagship[1]}"
        res["observations"] = observations
        res["findings"] = findings
        path = os.path.join(out, f"assessment-results-{fw}.json")
        with open(path, "w") as f:
            json.dump(ar, f, indent=2, ensure_ascii=False)
            f.write("\n")
        try:
            AssessmentResults.oscal_read(pathlib.Path(path))
        except Exception as e:  # a document trestle cannot read is no evidence
            print(f"{path} does not parse as OSCAL assessment results: {e}", file=sys.stderr)
            sys.exit(2)

    with open(os.path.join(out, "verdict.json"), "w") as f:
        json.dump(verdict, f, indent=2)
    write_summary(out, m, verdict, run_url, flagship)
    total = sum(len(s) for s in verdict["frameworks"].values())
    ok = sum(1 for s in verdict["frameworks"].values() for v in s.values() if v["state"] == "satisfied")
    print(f"== assessment results written: {ok} of {total} controls satisfied in this run")


def write_summary(out, m, verdict, run_url, flagship):
    lines = [f"# Evidence: {flagship[0]} {flagship[1]}", "",
             f"Run: {run_url}" + (f" (plant: `{verdict['plant']}`)" if verdict["plant"] else ""), "",
             "| Framework | Control | State | Policies | Engines | Tests |", "|---|---|---|---|---|---|"]
    for c in m["controls"]:
        s = verdict["frameworks"][c["framework"]][c["control"]]
        engines = sorted({e for r in c["rules"] for e, _ in checks_of(r, m["rules"][r])})
        lines.append(f"| {m['frameworks'][c['framework']]['title']} | {c['control']} | {s['state']} | "
                     f"{', '.join(c['rules'])} | {', '.join(engines) or 'tests only'} | {', '.join(c['proven_by'])} |")
    lines += ["", "## Admission tests", "", "| Test | Passed | What happened |", "|---|---|---|"]
    for name, t in verdict["tests"].items():
        lines.append(f"| {name} | {'yes' if t['passed'] else 'NO'} | {t['why'].replace('|', '/')} |")
    failing = [(fw, k, v) for fw, s in verdict["frameworks"].items() for k, v in s.items() if v["why"]]
    if failing:
        lines += ["", "## Not satisfied, and why", ""]
        lines += [f"- {fw} {k}: {'; '.join(v['why'])}" for fw, k, v in failing]
    with open(os.path.join(out, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
