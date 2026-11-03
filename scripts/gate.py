#!/usr/bin/env python3
"""gate.py EVIDENCE_DIR [--plant PLANT] - the gate, read from the evidence itself.

Reads the assessment results scripts/evidence.py wrote (the documents that
are signed and attached to releases), parses each with compliance-trestle's
OSCAL models, and fails when:

1. a control mapping/controls.yaml names has no finding in its framework's
   assessment results, or more than one;
2. a finding's state is anything but "satisfied";
3. an admission test failed, including one no control rests on (the
   layered refusal, model-by-tag) and one the run recorded that the mapping
   does not name.

Exits 0 when none of these, 1 when any, 2 when the evidence cannot be read:
a missing or unreadable document is a failure, never a pass.

With --plant, the run was broken on purpose (README, "The plants"), and the
gate must catch it for the planted reason: it exits 0 only if every control
resting on the planted policy is not satisfied and at least one admission
test that policy must refuse failed. A plant the gate lets through, or
catches only for some other reason, exits 1.

With E2E_RESULTS set, it also writes what it decided there, check by check,
for scripts/status.py and the branch `status`: {"checks": [{"state",
"name"}], "measured": [...]}. A run judged on its own has one check per
control and one per admission test, PASS only where the gate found nothing
wrong with it, and a measured line each for the controls, the planted pods
and the control pods. A plant's run has one check, whether the plant was
caught, since its controls are meant to fail; evidence the gate cannot read
is one failed check.
"""
import argparse
import json
import os
import pathlib
import sys

from ruamel.yaml import YAML
from trestle.oscal.assessment_results import AssessmentResults

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUR_NS = "https://github.com/heyvaldemar/kubernetes-oscal-evidence/ns"


def read(evidence, mapping):
    """{(framework, control): [states]} from the assessment results, and the failed tests."""
    found = {}
    for fw in mapping["frameworks"]:
        path = pathlib.Path(evidence) / f"assessment-results-{fw}.json"
        try:
            ar = AssessmentResults.oscal_read(path)
        except Exception as e:
            raise SystemExit(f"cannot read {path}: {e}")
        if ar is None:
            raise SystemExit(f"cannot read {path}")
        for result in ar.results:
            for f in result.findings or []:
                control = next((p.value for p in f.props or [] if p.name == "control" and str(p.ns) == OUR_NS), None)
                if control is not None:
                    found.setdefault((fw, control), []).append((f.target.status.state.value
                                                                if hasattr(f.target.status.state, "value")
                                                                else str(f.target.status.state),
                                                                f.description))
    try:
        verdict = json.load(open(os.path.join(evidence, "verdict.json")))
    except (OSError, ValueError) as e:
        raise SystemExit(f"cannot read verdict.json: {e}")
    failed_tests = {k: v["why"] for k, v in verdict["tests"].items() if not v["passed"]}
    return found, failed_tests


def judge(mapping, found, failed_tests):
    """Every failure the gate sees, as (framework, control or None, why)."""
    failures = []
    for c in mapping["controls"]:
        key = (c["framework"], c["control"])
        states = found.get(key, [])
        if len(states) != 1:
            failures.append((*key, f"{len(states)} findings in the assessment results; there must be one"))
            continue
        state, why = states[0]
        if state != "satisfied":
            failures.append((*key, f"{state}: {why}"))
    for test, why in failed_tests.items():
        failures.append(("tests", test, why))
    return failures


def planted(mapping, plant):
    """The controls a plant must turn not satisfied, and the tests of which at least one must fail."""
    kind, _, policy = plant.partition(":")
    if kind == "phantom-mapping":
        policy = "verify-models"
    if kind not in ("remove", "audit", "phantom-mapping") or policy not in mapping["rules"]:
        raise SystemExit(f"unknown plant {plant}")
    controls = {(c["framework"], c["control"]) for c in mapping["controls"] if policy in c["rules"]}
    tests = {t for t, spec in mapping["tests"].items() if policy in spec.get("by", [])}
    return controls, tests


def check_state(ok):
    return "PASS" if ok else "FAIL"


def results(mapping, failures, failed_tests):
    """The gate's verdicts on a run judged on its own, as scripts/status.py reads them."""
    failed = {(fw, what): why for fw, what, why in failures}
    checks = []
    for c in mapping["controls"]:
        key = (c["framework"], c["control"])
        checks.append({"state": check_state(key not in failed),
                       "name": f"{mapping['frameworks'][c['framework']]['title']} {c['control']}: "
                               f"{failed.get(key, 'satisfied')}"})
    for test in list(mapping["tests"]) + sorted(set(failed_tests) - set(mapping["tests"])):
        spec = mapping["tests"].get(test, {})
        did = "admitted" if spec.get("outcome") == "admitted" else f"refused by {' or '.join(spec.get('by', []))}"
        checks.append({"state": check_state(test not in failed_tests), "name": f"{test}: {failed_tests.get(test, did)}"})
    controls = len(mapping["controls"])
    satisfied = controls - len({k for k in failed if k[0] != "tests"})
    refused = [t for t, spec in mapping["tests"].items() if spec["outcome"] == "refused"]
    admitted = [t for t, spec in mapping["tests"].items() if spec["outcome"] == "admitted"]
    return {"checks": checks, "measured": [
        f"controls satisfied: {satisfied} of {controls}",
        f"planted pods refused: {sum(t not in failed_tests for t in refused)} of {len(refused)}",
        f"control pods admitted: {sum(t not in failed_tests for t in admitted)} of {len(admitted)}",
    ]}


def emit(doc):
    """Writes the gate's verdicts to $E2E_RESULTS, when it is set."""
    path = os.environ.get("E2E_RESULTS")
    if path:
        with open(path, "w") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence")
    ap.add_argument("--plant")
    args = ap.parse_args()
    # Always the committed mapping: the plant that names a policy that does
    # not exist changes the mapping the run used, never the one it is judged by.
    mapping = YAML(typ="safe").load(open(os.path.join(ROOT, "mapping", "controls.yaml")))
    try:
        found, failed_tests = read(args.evidence, mapping)
    except SystemExit as e:
        print(f"gate: {e}", file=sys.stderr)
        emit({"checks": [{"state": "FAIL", "name": f"the evidence: {e}"}], "measured": []})
        sys.exit(2)
    failures = judge(mapping, found, failed_tests)
    for fw, what, why in failures:
        print(f"FAIL {fw} {what}: {why}")
    passed = len(mapping["controls"]) - len({(f, w) for f, w, _ in failures if f != "tests"})
    print(f"== {passed} of {len(mapping['controls'])} controls satisfied, "
          f"{len(failed_tests)} admission test(s) failed")
    if not args.plant:
        emit(results(mapping, failures, failed_tests))
        sys.exit(1 if failures else 0)
    must, its_tests = planted(mapping, args.plant)
    caught = {(f, w) for f, w, _ in failures}
    missed = sorted(must - caught)
    failed_own = sorted(its_tests & set(failed_tests))
    if not missed and failed_own:
        why = ("caught: "
               + (f"every control resting on it is not satisfied ({', '.join(sorted(c for _, c in must))}), and "
                  if must else "no control rests on it, and ")
               + f"its own tests failed ({', '.join(failed_own)})")
        print(f"== plant {args.plant} {why}")
        emit({"checks": [{"state": check_state(True), "name": f"plant {args.plant}: {why}"}], "measured": []})
        sys.exit(0)
    why = "NOT caught: " + (f"still satisfied: {missed}" if missed else "none of the tests its policy must refuse failed")
    print(f"== plant {args.plant} {why}")
    emit({"checks": [{"state": check_state(False), "name": f"plant {args.plant}: {why}"}], "measured": []})
    sys.exit(1)


if __name__ == "__main__":
    main()
