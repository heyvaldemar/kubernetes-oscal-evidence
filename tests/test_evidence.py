"""The gate's own proof: each rule is shown the input that breaks it, and must fail.

Run with the packages in requirements.lock, from the repository root:

    python3 -m unittest discover -s tests

The fixtures in tests/fixtures/ are one real run's files (scripts/run.sh,
recorded in tests/fixtures/README.md): Kyverno's reports as the cluster held
them, the admission tests as the API server answered them, and the evidence
built from them. Each test copies what it needs and breaks one thing.

scripts/mutate.py runs this suite against copies of the scripts with one
rule switched off at a time (tests/plants.tsv); each must make a named test
here fail. SCRIPTS_DIR points the imports at such a copy.
"""
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = pathlib.Path(os.environ.get("SCRIPTS_DIR", ROOT / "scripts"))
sys.path.insert(0, str(SCRIPTS))
FIX = ROOT / "tests" / "fixtures"

import collect  # noqa: E402
import component  # noqa: E402
import evidence  # noqa: E402
import gate  # noqa: E402
from ruamel.yaml import YAML  # noqa: E402

MAPPING = YAML(typ="safe").load(open(ROOT / "mapping" / "controls.yaml"))


def load(name):
    return json.load(open(FIX / name))


class Collect(unittest.TestCase):
    """C2P reads Kyverno's reports only after two changes, and there must be no third."""

    def setUp(self):
        self.reports = load("policyreports.json")["items"]

    def test_scope_copied_into_each_result(self):
        for rep in self.reports:
            out = collect.scoped(rep)
            for res in out["results"]:
                self.assertEqual(res["resources"], [rep["scope"]])

    def test_message_filled_where_kyverno_gave_none(self):
        empty = [r for rep in self.reports for r in rep["results"] if not r.get("message")]
        self.assertTrue(empty, "the fixture must hold passing results with no message, as Kyverno writes them")
        for rep in self.reports:
            for res in collect.scoped(rep)["results"]:
                self.assertTrue(res["message"].strip())

    def test_nothing_else_changes(self):
        for rep in self.reports:
            out = collect.scoped(rep)
            for before, after in zip(rep["results"], out["results"]):
                after = dict(after)
                after.pop("resources")
                if not before.get("message"):
                    self.assertEqual(after.pop("message"), f"{before['result']}; Kyverno gave no message")
                self.assertEqual({k: v for k, v in before.items() if k not in ("resources",)
                                  and (k != "message" or v)}, after)
            self.assertEqual({k: v for k, v in rep.items() if k != "results"},
                             {k: v for k, v in out.items() if k != "results"})

    def test_input_left_as_it_was(self):
        before = copy.deepcopy(self.reports)
        for rep in self.reports:
            collect.scoped(rep)
        self.assertEqual(before, self.reports)


class Tests(unittest.TestCase):
    """An admission test passes only if the right policy refused it, for the right reason."""

    def setUp(self):
        self.recorded = {t["test"]: t for t in load("admission-tests.json")["tests"]}

    def judge(self, name, **change):
        rec = copy.deepcopy(self.recorded)
        rec[name].update(change)
        return evidence.judge_test(name, MAPPING["tests"][name], rec)

    def test_the_real_run_passes_every_test(self):
        for name, spec in MAPPING["tests"].items():
            passed, why = evidence.judge_test(name, spec, self.recorded)
            self.assertTrue(passed, f"{name}: {why}")

    def test_admitted_when_it_must_be_refused(self):
        self.assertFalse(self.judge("model-unsigned", admitted=True, refused_by=None)[0])

    def test_refused_when_it_must_be_admitted(self):
        self.assertFalse(self.judge("model-signed", admitted=False, refused_by="verify-models")[0])

    def test_refused_by_the_wrong_policy(self):
        # model-volumes gone, verify-models refuses the volume from elsewhere instead.
        self.assertFalse(self.judge("volume-elsewhere", refused_by="verify-models")[0])

    def test_refused_without_the_expected_words(self):
        self.assertFalse(self.judge("model-unsigned", message="Policy verify-models error: registry unreachable")[0])

    def test_not_recorded(self):
        rec = dict(self.recorded)
        rec.pop("kyverno-away")
        self.assertFalse(evidence.judge_test("kyverno-away", MAPPING["tests"]["kyverno-away"], rec)[0])


class Decide(unittest.TestCase):
    """A control is satisfied only on Kyverno's reports, C2P's verdict and its tests together."""

    def setUp(self):
        self.control = next(c for c in MAPPING["controls"] if c["control"] == "cm-14")
        self.ok_tests = {t: (True, "ok") for t in MAPPING["tests"]}
        self.subject = {"title": "Pod inference/model-server",
                        "props": [{"name": "result", "ns": evidence.TRESTLE_NS, "value": "pass"}]}
        self.by_rule = {"verify-models": [{"uuid": "u", "subjects": [self.subject]}],
                        "models-need-kyverno": [{"uuid": "v", "subjects": [self.subject]}]}

    def decide(self, c2p_failed=(), by_rule=None, tests=None):
        return evidence.decide(self.control, MAPPING["rules"], set(c2p_failed),
                               self.by_rule if by_rule is None else by_rule, tests or self.ok_tests)[0]

    def test_all_good_is_satisfied(self):
        self.assertEqual(self.decide(), [])

    def test_c2p_not_satisfied_is_never_overruled(self):
        self.assertTrue(self.decide(c2p_failed={"cm-14_smt"}))

    def test_no_pod_reported_is_not_satisfied(self):
        self.assertTrue(self.decide(by_rule=dict(self.by_rule, **{"verify-models": [{"uuid": "u", "subjects": []}]})))
        self.assertTrue(self.decide(by_rule={}))

    def test_a_failed_pod_is_not_satisfied(self):
        bad = copy.deepcopy(self.subject)
        bad["props"][0]["value"] = "fail"
        self.assertTrue(self.decide(by_rule=dict(self.by_rule, **{"verify-models": [{"uuid": "u", "subjects": [self.subject, bad]}]})))

    def test_an_errored_pod_is_not_satisfied(self):
        bad = copy.deepcopy(self.subject)
        bad["props"][0]["value"] = "error"
        self.assertTrue(self.decide(by_rule=dict(self.by_rule, **{"verify-models": [{"uuid": "u", "subjects": [bad]}]})))

    def test_a_failed_test_is_not_satisfied(self):
        tests = dict(self.ok_tests, **{"model-stranger": (False, "admitted")})
        self.assertTrue(self.decide(tests=tests))

    def test_no_posture_rule_rests_on_tests_alone(self):
        # egress-node: Kyverno cannot report it, so its tests are all there is.
        control = {"control": "x-1", "rules": ["egress-node"],
                   "proven_by": ["egress-toleration", "egress-tolerate-all", "egress-node-name", "ordinary-pod"]}
        self.assertEqual(evidence.decide(control, MAPPING["rules"], set(), {}, self.ok_tests)[0], [])
        tests = dict(self.ok_tests, **{"egress-toleration": (False, "admitted")})
        self.assertTrue(evidence.decide(control, MAPPING["rules"], set(), {}, tests)[0])


class Mapping(unittest.TestCase):
    """A mapping that names what does not exist is refused before anything runs, each for its own reason."""

    def errors(self, edit):
        m = copy.deepcopy(MAPPING)
        edit(m)
        return "\n".join(component.check_mapping(m))

    def control(self, m, cid):
        return next(c for c in m["controls"] if c["control"] == cid)

    def test_the_committed_mapping_is_clean(self):
        self.assertEqual(component.check_mapping(MAPPING), [])

    def test_a_policy_that_does_not_exist(self):
        # The phantom-mapping plant's change: the policy renamed everywhere the
        # mapping names it, so only the lookup in the flagship's file can tell.
        text = open(ROOT / "mapping" / "controls.yaml").read()
        m = YAML(typ="safe").load(re.sub(r"verify-models([^.]|$)", r"verify-model-signatures\1", text, flags=re.M))
        errors = component.check_mapping(m)
        self.assertTrue(any("defines no policy named verify-model-signatures" in e for e in errors), errors)

    def test_a_test_that_does_not_exist(self):
        def edit(m):
            m["tests"]["model-unsigend"] = m["tests"]["model-unsigned"]
            self.control(m, "cm-14")["proven_by"].append("model-unsigend")
        self.assertIn("no such planted pod", self.errors(edit))

    def test_a_control_not_in_the_catalog(self):
        def edit(m):
            self.control(m, "cm-14")["control"] = "cm-99"
        self.assertIn("not a control in NIST_SP-800-53_rev5_catalog.json", self.errors(edit))

    def test_a_control_never_shown_a_violation(self):
        def edit(m):
            self.control(m, "cm-14")["proven_by"] = ["model-signed"]
        self.assertIn("no test that must be refused", self.errors(edit))

    def test_a_test_credited_to_a_policy_that_does_not_refuse_it(self):
        def edit(m):
            self.control(m, "cm-14")["proven_by"].append("image-by-tag")
        self.assertIn("not by this control's rules", self.errors(edit))

    def test_a_matrix_row_that_does_not_exist(self):
        def edit(m):
            self.control(m, "cm-14")["matrix"] = ["LLM11:2025"]
        self.assertIn("is not in the pinned control-to-test matrix", self.errors(edit))

    def test_a_control_on_no_matrix_row(self):
        def edit(m):
            self.control(m, "sr-11")["matrix"] = []
        self.assertIn("names no row of the control-to-test matrix", self.errors(edit))

    def test_an_ssdf_control_that_is_not_its_own_row(self):
        def edit(m):
            self.control(m, "PW.4.4")["matrix"] = ["LLM03:2025"]
        self.assertIn("must name its own", self.errors(edit))


class Gate(unittest.TestCase):
    """The gate reads the signed documents, and fails on anything short of every control satisfied."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = pathlib.Path(self.tmp) / "evidence"
        shutil.copytree(FIX / "evidence", self.dir)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_gate(self, *args, says=None):
        p = subprocess.run([sys.executable, str(SCRIPTS / "gate.py"), str(self.dir), *args],
                           capture_output=True, text=True)
        if says is not None:
            self.assertIn(says, p.stdout + p.stderr)
        return p.returncode

    def edit_finding(self, fw, control, edit):
        path = self.dir / f"assessment-results-{fw}.json"
        doc = json.load(open(path))
        findings = doc["assessment-results"]["results"][0]["findings"]
        for f in list(findings):
            if any(p["name"] == "control" and p["value"] == control for p in f["props"]):
                if edit(f) is False:
                    findings.remove(f)
        json.dump(doc, open(path, "w"))

    def test_the_real_run_passes(self):
        self.assertEqual(self.run_gate(), 0)

    def test_a_control_not_satisfied(self):
        def edit(f):
            f["target"]["status"]["state"] = "not-satisfied"
        self.edit_finding("nist_ssdf", "PW.4.4", edit)
        self.assertEqual(self.run_gate(), 1)

    def test_a_control_with_no_finding(self):
        self.edit_finding("nist_800_53", "sr-11", lambda f: False)
        self.assertEqual(self.run_gate(says="FAIL nist_800_53 sr-11: 0 findings"), 1)

    def test_a_failed_test(self):
        v = json.load(open(self.dir / "verdict.json"))
        v["tests"]["model-by-tag"] = {"passed": False, "why": "admitted"}
        json.dump(v, open(self.dir / "verdict.json", "w"))
        self.assertEqual(self.run_gate(), 1)

    def test_a_missing_document(self):
        (self.dir / "assessment-results-nist_ai_rmf.json").unlink()
        self.assertEqual(self.run_gate(says="cannot read"), 2)

    def test_a_document_trestle_cannot_read(self):
        (self.dir / "assessment-results-nist_800_53.json").write_text('{"assessment-results": {"uuid": "x"}}')
        self.assertEqual(self.run_gate(says="cannot read"), 2)

    def test_a_plant_not_caught(self):
        self.assertEqual(self.run_gate("--plant", "remove:verify-models"), 1)

    def fail_test(self, name):
        v = json.load(open(self.dir / "verdict.json"))
        v["tests"][name] = {"passed": False, "why": "admitted; it must be refused"}
        json.dump(v, open(self.dir / "verdict.json", "w"))

    def fail_controls_of(self, policy):
        for c in MAPPING["controls"]:
            if policy in c["rules"]:
                def edit(f):
                    f["target"]["status"]["state"] = "not-satisfied"
                self.edit_finding(c["framework"], c["control"], edit)

    def test_a_plant_caught(self):
        self.fail_controls_of("verify-models")
        self.fail_test("model-unsigned")
        self.assertEqual(self.run_gate("--plant", "remove:verify-models", says="caught"), 0)

    def test_a_plant_caught_for_another_reason(self):
        self.fail_controls_of("carried-images")
        self.fail_test("image-by-tag")
        self.assertEqual(self.run_gate("--plant", "remove:verify-models"), 1)

    def test_a_plant_whose_own_tests_all_passed(self):
        # Every control on verify-models down, but nothing it must refuse got in:
        # the gate failed for some other reason than the plant.
        self.fail_controls_of("verify-models")
        self.fail_test("image-by-tag")
        self.assertEqual(self.run_gate("--plant", "remove:verify-models"), 1)

    def test_a_plant_with_a_control_still_satisfied(self):
        # The policy's own test failed, but one control resting on it is still
        # called satisfied: the evidence missed what the plant broke.
        self.fail_controls_of("verify-models")
        self.fail_test("model-unsigned")
        def edit(f):
            f["target"]["status"]["state"] = "satisfied"
        self.edit_finding("nist_ssdf", "PW.4.4", edit)
        self.assertEqual(self.run_gate("--plant", "remove:verify-models", says="still satisfied"), 1)

    def test_a_plant_no_control_rests_on(self):
        self.assertEqual(self.run_gate("--plant", "remove:egress-node"), 1)
        self.fail_test("egress-toleration")
        self.assertEqual(self.run_gate("--plant", "remove:egress-node", says="no control rests on it"), 0)


if __name__ == "__main__":
    unittest.main()
