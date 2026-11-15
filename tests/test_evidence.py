"""The gate's own proof: each rule is shown the input that breaks it, and must fail.

Run with the packages in requirements.lock, from the repository root:

    python3 -m unittest discover -s tests

The fixtures in tests/fixtures/ are one real run's files (tests/e2e/run.sh,
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
import importlib.util  # noqa: E402
from ruamel.yaml import YAML  # noqa: E402

# scripts/tests.py, by its path: the name "tests" is this directory's too.
_spec = importlib.util.spec_from_file_location("admission_tests", SCRIPTS / "tests.py")
admission_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(admission_tests)

MAPPING = YAML(typ="safe").load(open(ROOT / "mapping" / "controls.yaml"))


def load(name):
    return json.load(open(FIX / name))


class Collect(unittest.TestCase):
    """Which workloads each policy must have been judged on: the reach both engines share."""

    def test_reach_of_each_policy(self):
        for rule in ("verify-models", "model-volumes", "models-need-kyverno"):
            self.assertTrue(collect.reaches(rule, "inference"))
            self.assertFalse(collect.reaches(rule, "default"), rule)
        self.assertTrue(collect.reaches("carried-images", "default"))
        self.assertTrue(collect.reaches("carried-images", "inference"))


class DryRun(unittest.TestCase):
    """The API server's dry run: a pass is an admission the run can stand behind, and nothing else."""

    def setUp(self):
        self.pod = {"metadata": {"name": "model-server-abc", "namespace": "inference", "uid": "u",
                                 "resourceVersion": "1", "ownerReferences": [{"kind": "ReplicaSet"}],
                                 "labels": {"app": "model-server"}},
                    "spec": {"nodeName": "worker", "priority": 0, "containers": [{"name": "c", "image": "i"}]},
                    "status": {"phase": "Running"}}

    def outcome(self, answer, seen=("carried-images",), pod=True):
        return admission_tests.dry_run_outcome("vap-carried-images", "carried-images",
                                               "inference/deployment/model-server",
                                               self.pod if pod else None, answer, set(seen), "2026-11-16T00:00:00Z")

    def test_admitted_and_the_policy_seen_refusing_is_a_pass(self):
        o = self.outcome({"admitted": True, "refused_by": None, "message": "created (server dry run)"})
        self.assertEqual((o["result"], o["checkId"], o["resourceId"]),
                         ("pass", "vap-carried-images", "v1/Pod/inference/model-server-abc"))

    def test_admitted_but_the_policy_never_refused(self):
        # remove:carried-images: no binding, every dry run admitted, and that proves nothing.
        o = self.outcome({"admitted": True, "refused_by": None, "message": ""}, seen=("verify-models",))
        self.assertEqual(o["result"], "error")

    def test_refused_by_the_policy_is_a_failure(self):
        o = self.outcome({"admitted": False, "refused_by": "carried-images", "message": "by digest"})
        self.assertEqual(o["result"], "fail")

    def test_refused_by_another_policy_is_unknown(self):
        o = self.outcome({"admitted": False, "refused_by": "verify-models", "message": "unsigned"})
        self.assertEqual(o["result"], "error")

    def test_no_running_pod_is_unknown(self):
        self.assertEqual(self.outcome({}, pod=False)["result"], "error")

    def test_sent_again_as_a_new_pod(self):
        doc = json.loads(admission_tests.as_new(self.pod, "model-server-abc-dry-run"))
        self.assertEqual(doc["metadata"], {"name": "model-server-abc-dry-run", "namespace": "inference",
                                           "labels": {"app": "model-server"}})
        self.assertEqual(doc["spec"], {"containers": [{"name": "c", "image": "i"}]})
        self.assertNotIn("status", doc)


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
    """A control is satisfied only on every engine's checks, C2P's posture and its tests together."""

    def setUp(self):
        # sr-11 rests on three policies, two of them judged by both engines: the most checks of any control.
        self.control = next(c for c in MAPPING["controls"] if c["control"] == "sr-11")
        self.ok_tests = {t: (True, "ok") for t in MAPPING["tests"]}
        self.subject = {"title": "Pod inference/model-server", "props": [{"name": "result", "value": "pass"}]}
        self.by_check = {c: [{"uuid": c, "subjects": [self.subject]}]
                         for c in ("verify-models", "models-need-kyverno", "carried-images",
                                   "vap-models-need-kyverno", "vap-carried-images")}
        self.posture = {"sr-11": {"state": "satisfied", "remarks": "all passing", "assessed": 5, "expected": 5}}

    def decide(self, posture=None, by_check=None, tests=None):
        return evidence.decide(self.control, MAPPING["rules"], self.posture if posture is None else posture,
                               self.by_check if by_check is None else by_check, tests or self.ok_tests)[0]

    def without(self, check):
        return {k: v for k, v in self.by_check.items() if k != check}

    def test_all_good_is_satisfied(self):
        self.assertEqual(self.decide(), [])

    def test_c2p_posture_not_satisfied_is_never_overruled(self):
        for state in ("not-satisfied", "not-assessed"):
            self.assertTrue(self.decide(posture={"sr-11": dict(self.posture["sr-11"], state=state)}), state)
        self.assertTrue(self.decide(posture={}))

    def test_an_engine_that_reported_nothing(self):
        # C2P's posture calls the control satisfied, 4 of 5 expected checks reported.
        posture = {"sr-11": dict(self.posture["sr-11"], assessed=4)}
        why = self.decide(posture=posture, by_check=self.without("vap-carried-images"))
        self.assertEqual(why, ["the API server's dry run reported no running pod for carried-images"])

    def test_no_pod_reported_is_not_satisfied(self):
        self.assertTrue(self.decide(by_check=dict(self.by_check, **{"verify-models": [{"uuid": "u", "subjects": []}]})))
        self.assertTrue(self.decide(by_check={}))

    def test_a_failed_pod_is_not_satisfied(self):
        bad = copy.deepcopy(self.subject)
        bad["props"][0]["value"] = "fail"
        self.assertTrue(self.decide(by_check=dict(self.by_check, **{"vap-carried-images": [{"uuid": "u", "subjects": [self.subject, bad]}]})))

    def test_an_errored_pod_is_not_satisfied(self):
        bad = copy.deepcopy(self.subject)
        bad["props"][0]["value"] = "error"
        self.assertTrue(self.decide(by_check=dict(self.by_check, **{"verify-models": [{"uuid": "u", "subjects": [bad]}]})))

    def test_a_failed_test_is_not_satisfied(self):
        tests = dict(self.ok_tests, **{"model-stranger": (False, "admitted")})
        self.assertTrue(self.decide(tests=tests))

    def test_no_posture_rule_rests_on_tests_alone(self):
        # egress-node: no engine judges it, so its tests are all there is.
        control = {"control": "x-1", "rules": ["egress-node"],
                   "proven_by": ["egress-toleration", "egress-tolerate-all", "egress-node-name", "ordinary-pod"]}
        posture = {"x-1": {"state": "satisfied", "remarks": "", "assessed": 0, "expected": 0}}
        self.assertEqual(evidence.decide(control, MAPPING["rules"], posture, {}, self.ok_tests)[0], [])
        tests = dict(self.ok_tests, **{"egress-toleration": (False, "admitted")})
        self.assertTrue(evidence.decide(control, MAPPING["rules"], posture, {}, tests)[0])


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
            self.control(m, "si-7")["proven_by"].append("model-unsigend")
        self.assertIn("no such planted pod", self.errors(edit))

    def test_a_control_not_in_the_catalog(self):
        def edit(m):
            self.control(m, "si-7")["control"] = "cm-99"
        self.assertIn("not a control in NIST_SP-800-53_rev5_catalog.json", self.errors(edit))

    def test_a_control_never_shown_a_violation(self):
        def edit(m):
            self.control(m, "si-7")["proven_by"] = ["model-signed"]
        self.assertIn("no test that must be refused", self.errors(edit))

    def test_a_test_credited_to_a_policy_that_does_not_refuse_it(self):
        def edit(m):
            self.control(m, "si-7")["proven_by"].append("image-by-tag")
        self.assertIn("not by this control's rules", self.errors(edit))

    def test_a_matrix_row_that_does_not_exist(self):
        def edit(m):
            self.control(m, "si-7")["matrix"] = ["LLM11:2025"]
        self.assertIn("is not in the pinned control-to-test matrix", self.errors(edit))

    def test_a_control_on_no_matrix_row(self):
        def edit(m):
            self.control(m, "sr-11")["matrix"] = []
        self.assertIn("names no row of the control-to-test matrix", self.errors(edit))

    def test_dry_run_on_a_policy_the_api_server_does_not_judge(self):
        def edit(m):
            m["rules"]["verify-models"]["dry_run"] = True
        self.assertIn("only a ValidatingAdmissionPolicy answers a dry run", self.errors(edit))

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

    def silence(self, control_ids, why="the API server's dry run reported no running pod for carried-images"):
        for c in MAPPING["controls"]:
            if c["control"] in control_ids:
                def edit(f):
                    f["target"]["status"]["state"] = "not-satisfied"
                    f["description"] = why
                self.edit_finding(c["framework"], c["control"], edit)

    def test_a_silent_plant_caught(self):
        self.assertEqual(self.run_gate("--plant", "silent:api-server", says="NOT caught"), 1)
        self.silence({"si-7", "sr-11", "cm-7.5"})
        self.assertEqual(self.run_gate("--plant", "silent:api-server", says="caught"), 0)

    def test_a_silent_plant_with_a_control_still_satisfied(self):
        self.silence({"si-7", "sr-11"})
        self.assertEqual(self.run_gate("--plant", "silent:api-server", says="still satisfied"), 1)

    def test_a_silent_plant_caught_for_another_reason(self):
        # Every control on the engine down, but one of them for something else.
        self.silence({"si-7", "sr-11"})
        self.silence({"cm-7.5"}, why="test image-by-tag: admitted; it must be refused")
        self.assertEqual(self.run_gate("--plant", "silent:api-server", says="another reason"), 1)

    # What the gate writes to $E2E_RESULTS is what the branch `status` and
    # heyvaldemar.com show: it must say FAIL wherever the gate did.

    def gate_results(self, *args):
        out = pathlib.Path(self.tmp) / "e2e-results.json"
        p = subprocess.run([sys.executable, str(SCRIPTS / "gate.py"), str(self.dir), *args],
                           capture_output=True, text=True, env=dict(os.environ, E2E_RESULTS=str(out)))
        return p.returncode, json.load(open(out))

    def counts(self):
        tests = MAPPING["tests"].values()
        return (len(MAPPING["controls"]), sum(t["outcome"] == "refused" for t in tests),
                sum(t["outcome"] == "admitted" for t in tests))

    def test_results_of_the_real_run(self):
        code, doc = self.gate_results()
        controls, refused, admitted = self.counts()
        self.assertEqual(code, 0)
        self.assertEqual(len(doc["checks"]), controls + len(MAPPING["tests"]))
        self.assertEqual({c["state"] for c in doc["checks"]}, {"PASS"})
        self.assertEqual(doc["measured"], [f"controls satisfied: {controls} of {controls}",
                                           f"planted pods refused: {refused} of {refused}",
                                           f"control pods admitted: {admitted} of {admitted}"])
        for line in doc["measured"]:  # the site folds "X · label: value" lines into a table
            self.assertNotIn(" · ", line)

    def test_results_name_what_failed(self):
        def edit(f):
            f["target"]["status"]["state"] = "not-satisfied"
        self.edit_finding("nist_ssdf", "PW.4.4", edit)
        self.fail_test("model-unsigned")
        code, doc = self.gate_results()
        self.assertEqual(code, 1)
        failed = [c["name"] for c in doc["checks"] if c["state"] == "FAIL"]
        self.assertEqual(len(failed), 2, failed)
        self.assertTrue(failed[0].startswith("NIST SP 800-218 SSDF v1.1 PW.4.4: not-satisfied"), failed)
        self.assertTrue(failed[1].startswith("model-unsigned: admitted"), failed)

    def test_results_count_what_failed(self):
        self.fail_test("model-unsigned")
        self.fail_test("ordinary-pod")
        code, doc = self.gate_results()
        controls, refused, admitted = self.counts()
        self.assertEqual(code, 1)
        self.assertEqual(doc["measured"][1:], [f"planted pods refused: {refused - 1} of {refused}",
                                               f"control pods admitted: {admitted - 1} of {admitted}"])

    def test_results_of_a_plant(self):
        code, doc = self.gate_results("--plant", "remove:verify-models")
        self.assertEqual((code, [c["state"] for c in doc["checks"]], doc["measured"]), (1, ["FAIL"], []))
        self.assertTrue(doc["checks"][0]["name"].startswith("plant remove:verify-models: NOT caught"))
        self.fail_controls_of("verify-models")
        self.fail_test("model-unsigned")
        code, doc = self.gate_results("--plant", "remove:verify-models")
        self.assertEqual((code, [c["state"] for c in doc["checks"]], doc["measured"]), (0, ["PASS"], []))
        self.assertTrue(doc["checks"][0]["name"].startswith("plant remove:verify-models: caught"))

    def test_results_when_the_evidence_cannot_be_read(self):
        (self.dir / "assessment-results-nist_ai_rmf.json").unlink()
        code, doc = self.gate_results()
        self.assertEqual((code, [c["state"] for c in doc["checks"]]), (2, ["FAIL"]))


if __name__ == "__main__":
    unittest.main()
