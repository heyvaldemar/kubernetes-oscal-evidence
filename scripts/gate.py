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
gate must catch it for the planted reason: it exits 0 only if the evidence
fails and every control resting on the planted policy is among the failures.
A plant the gate lets through exits 1.
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
    """The controls a plant must turn not satisfied."""
    kind, _, policy = plant.partition(":")
    if kind == "phantom-mapping":
        policy = "verify-models"
    if kind not in ("remove", "audit", "phantom-mapping") or policy not in mapping["rules"]:
        raise SystemExit(f"unknown plant {plant}")
    return {(c["framework"], c["control"]) for c in mapping["controls"] if policy in c["rules"]}


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
        sys.exit(2)
    failures = judge(mapping, found, failed_tests)
    for fw, what, why in failures:
        print(f"FAIL {fw} {what}: {why}")
    passed = len(mapping["controls"]) - len({(f, w) for f, w, _ in failures if f != "tests"})
    print(f"== {passed} of {len(mapping['controls'])} controls satisfied, "
          f"{len(failed_tests)} admission test(s) failed")
    if not args.plant:
        sys.exit(1 if failures else 0)
    must = planted(mapping, args.plant)
    caught = {(f, w) for f, w, _ in failures}
    missed = sorted(must - caught)
    if failures and not missed:
        print(f"== plant {args.plant} caught: every control resting on it is not satisfied "
              f"({', '.join(sorted(c for _, c in must))})")
        sys.exit(0)
    print(f"== plant {args.plant} NOT caught: still satisfied: {missed or 'nothing failed at all'}")
    sys.exit(1)


if __name__ == "__main__":
    main()
