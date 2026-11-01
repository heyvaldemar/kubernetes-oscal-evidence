#!/usr/bin/env python3
"""component.py [--check] - the OSCAL component definition, from mapping/controls.yaml.

Built with compliance-trestle's OSCAL models, in the shape C2P reads:

- a component of type "software" for the flagship's admission policies,
  carrying each policy as a rule (Rule_Id, Rule_Description) and, per
  framework, a control implementation whose implemented requirements name
  the rules that carry each control, the tests that prove it, and what it
  leaves out;
- a component of type "validation" titled "Kyverno", whose checks
  (Check_Id) are the policies Kyverno's PolicyReports describe. A policy
  whose posture the reports cannot judge (egress-node) is a rule with no
  check: C2P then makes no observation of it, and its tests alone judge it.

Before writing, every mapped control is looked up in its pinned NIST catalog
and every policy, test and rule name is checked against the flagship's
release, so a mapping that names something that does not exist stops here.
UUIDs are derived from names, so the same mapping gives the same file.

--check rebuilds the file and fails if the committed one differs.
--mapping and --out read and write elsewhere, and --unchecked skips the
lookups: only the plant that names a policy that does not exist uses them,
to show that the run catches such a mapping on its own as well.
"""
import argparse
import datetime
import glob
import json
import os
import sys
import uuid

from ruamel.yaml import YAML
from trestle.oscal import common
from trestle.oscal.component import (ComponentDefinition, ControlImplementation, DefinedComponent,
                                     ImplementedRequirement)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAGSHIP = os.path.join(ROOT, ".cache", "flagship", "src")
CATALOGS = os.path.join(ROOT, ".cache", "catalogs")
OUT = os.path.join(ROOT, "oscal", "component-definition.json")
TRESTLE_NS = "https://oscal-compass.github.io/compliance-trestle/schemas/oscal"
CD_NS = TRESTLE_NS + "/cd"
OUR_NS = "https://github.com/heyvaldemar/kubernetes-oscal-evidence/ns"
SEED = uuid.UUID("6f1c2a52-6c39-4d1e-9a0e-0d1b8f6a3c11")


def uid(*parts):
    return str(uuid.uuid5(SEED, "/".join(parts)))


def prop(name, value, ns=CD_NS, remarks=None):
    return common.Property(name=name, value=value, ns=ns, remarks=remarks)


def lock(path):
    rows = {}
    for line in open(os.path.join(ROOT, path)):
        if line.strip() and not line.startswith("#"):
            f = line.split()
            rows[f[0]] = f[1:]
    return rows


def statements(catalog):
    """Every control id in a catalog, with the id of its statement part."""
    out = {}

    def walk(controls):
        for c in controls or []:
            smt = next((p["id"] for p in c.get("parts", []) if p.get("name") == "statement" and p.get("id")), None)
            out[c["id"]] = smt
            walk(c.get("controls"))

    def groups(gs):
        for g in gs or []:
            walk(g.get("controls"))
            groups(g.get("groups"))

    cat = json.load(open(catalog))["catalog"]
    groups(cat.get("groups"))
    walk(cat.get("controls"))
    return out


def load_mapping(path):
    return YAML(typ="safe").load(open(path))


def check_mapping(m):
    """Everything the mapping names must exist. Returns a list of what does not."""
    errors = []
    flagship_tests = {os.path.basename(p)[:-5] for p in
                      glob.glob(os.path.join(FLAGSHIP, "tests/e2e/plants/*.yaml")) +
                      glob.glob(os.path.join(FLAGSHIP, "tests/e2e/plants-frontier/*.yaml"))}
    flagship_tests.add("kyverno-away")  # the game day step tests.py runs, from tests/e2e/gameday.sh
    for name, rule in m["rules"].items():
        path = os.path.join(FLAGSHIP, rule["file"])
        if not os.path.isfile(path):
            errors.append(f"rule {name}: {rule['file']} is not in the flagship's release")
        elif f"name: {name}\n" not in open(path).read():
            errors.append(f"rule {name}: {rule['file']} defines no policy named {name}")
        if rule.get("posture") not in ("kyverno", "none"):
            errors.append(f"rule {name}: posture must be kyverno or none")
    for test, t in m["tests"].items():
        if test not in flagship_tests:
            errors.append(f"test {test}: no such planted pod in the flagship's release")
        for r in t.get("by", []):
            if r not in m["rules"]:
                errors.append(f"test {test}: refused by {r}, which is not a rule here")
    for c in m["controls"]:
        cid = f"{c['framework']}/{c['control']}"
        if c["framework"] not in m["frameworks"]:
            errors.append(f"{cid}: unknown framework")
            continue
        catalog = os.path.join(CATALOGS, m["frameworks"][c["framework"]]["catalog"])
        if c["control"] not in statements(catalog):
            errors.append(f"{cid}: not a control in {m['frameworks'][c['framework']]['catalog']}")
        for r in c["rules"]:
            if r not in m["rules"]:
                errors.append(f"{cid}: rule {r} is not a policy here")
        for t in c["proven_by"]:
            if t not in m["tests"]:
                errors.append(f"{cid}: test {t} is not in the tests list")
            elif m["tests"][t]["outcome"] == "refused" and not set(m["tests"][t]["by"]) <= set(c["rules"]):
                errors.append(f"{cid}: test {t} is refused by {m['tests'][t]['by']}, not by this control's rules")
        if not any(m["tests"][t]["outcome"] == "refused" for t in c["proven_by"] if t in m["tests"]):
            errors.append(f"{cid}: no test that must be refused; a control never shown a violation proves nothing")
    return errors


def build(m):
    tag = lock("flagship.lock")["heyvaldemar/kubernetes-air-gapped-ai-agent"][0]
    catalogs = lock("catalogs.lock")
    rule_props = []
    check_props = []
    for i, (name, rule) in enumerate(m["rules"].items()):
        rs = f"rule_set_{i}"
        rule_props += [prop("Rule_Id", name, remarks=rs),
                       prop("Rule_Description", " ".join(rule["description"].split()), remarks=rs),
                       prop("policy-file", rule["file"], ns=OUR_NS, remarks=rs),
                       prop("policy-kind", rule["kind"], ns=OUR_NS, remarks=rs),
                       prop("posture", rule["posture"], ns=OUR_NS, remarks=rs)]
        if rule["posture"] == "kyverno":
            check_props += [prop("Rule_Id", name, remarks=rs),
                            prop("Check_Id", name, remarks=rs),
                            prop("Check_Description",
                                 f"Kyverno PolicyReport results for {name} on the pods running in the cluster",
                                 remarks=rs)]
    impls = []
    for fw, spec in m["frameworks"].items():
        reqs = []
        for c in [c for c in m["controls"] if c["framework"] == fw]:
            props = [prop("Rule_Id", r) for r in c["rules"]]
            props += [prop("proven-by", t, ns=OUR_NS) for t in c["proven_by"]]
            reqs.append(ImplementedRequirement(
                uuid=uid(fw, c["control"]), control_id=c["control"],
                description=" ".join(c["implementation"].split()),
                props=props, remarks="Not covered: " + " ".join(c["not_covered"].split())))
        impls.append(ControlImplementation(
            uuid=uid(fw), source=catalogs[spec["catalog"]][0],
            description=spec["title"],
            props=[prop("Framework_Short_Name", fw, ns=TRESTLE_NS)],
            implemented_requirements=reqs))
    software = DefinedComponent(
        uuid=uid("component", "admission"), type="software",
        title=f"kubernetes-air-gapped-ai-agent {tag} admission policies",
        description=("The admission policies of heyvaldemar/kubernetes-air-gapped-ai-agent at release "
                     f"{tag}, read from its signed source archive: Kyverno's verify-models and four "
                     "Kubernetes ValidatingAdmissionPolicies."),
        props=rule_props, control_implementations=impls)
    kyverno = DefinedComponent(
        uuid=uid("component", "kyverno"), type="validation", title="Kyverno",
        description="Kyverno as the policy validation point: its PolicyReports, read by C2P's Kyverno plugin.",
        props=check_props)
    return ComponentDefinition(
        uuid=uid("component-definition"),
        metadata=common.Metadata(
            title=f"Admission controls of kubernetes-air-gapped-ai-agent {tag}, mapped to NIST controls",
            last_modified=datetime.datetime.fromisoformat(m["last_modified"]),
            version=m["version"], oscal_version=common.OscalVersion("1.2.1"),
            remarks="Generated by scripts/component.py from mapping/controls.yaml."),
        components=[software, kyverno])


def render(cd):
    return json.dumps(json.loads(cd.oscal_serialize_json(pretty=False)), indent=2, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--mapping", default=os.path.join(ROOT, "mapping", "controls.yaml"))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--unchecked", action="store_true")
    args = ap.parse_args()
    m = load_mapping(args.mapping)
    errors = [] if args.unchecked else check_mapping(m)
    if errors:
        print("mapping/controls.yaml names what does not exist:\n  " + "\n  ".join(errors), file=sys.stderr)
        sys.exit(1)
    text = render(build(m))
    if args.check:
        if not os.path.exists(args.out) or open(args.out).read() != text:
            print("oscal/component-definition.json is not what mapping/controls.yaml gives; "
                  "run scripts/component.py and commit it", file=sys.stderr)
            sys.exit(1)
        print("== oscal/component-definition.json matches mapping/controls.yaml")
        return
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w").write(text)
    print(f"== wrote {os.path.relpath(args.out, ROOT)}: {len(m['rules'])} rules, {len(m['controls'])} controls")


if __name__ == "__main__":
    main()
