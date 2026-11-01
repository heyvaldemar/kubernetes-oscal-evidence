#!/usr/bin/env python3
"""tests.py OUT.json - the workloads, and the flagship's planted pods, on the cluster.

Three things, in this order, all recorded in OUT.json:

1. kyverno-away: the flagship's game day for its guard (tests/e2e/gameday.sh).
   Kyverno's admission controller is scaled to zero; once its webhook
   configuration is gone (Kyverno deletes it on the way down when it sees its
   Deployment at zero; if it has not, this deletes it, which is the case the
   guard exists for), the signed model is asked for and must be refused.
   Kyverno is then scaled back and must admit the signed model again.

2. The workloads that run and that PolicyReports describe: the model server
   (workload/model-server.yaml) and the flagship's ordinary pod beside the
   egress node. Under PLANT=audit:verify-models, also a server that mounts a
   model nobody signed.

3. Every planted pod in the flagship's tests/e2e/plants and
   tests/e2e/plants-frontier, asked for with a server-side dry run: what the
   API server answered, and which policy refused it. Dry runs are not
   recorded in PolicyReports, so the planted pods never enter the posture.

This records what happened. Whether it is what each control needs is
decided by scripts/evidence.py against mapping/controls.yaml.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, ".cache", "run")
FLAGSHIP = os.path.join(ROOT, ".cache", "flagship", "src")
REG = "registry.boundary.internal:5000"
PLANT = os.environ.get("PLANT", "")
HOOK = "ivpol.validate.kyverno.svc-fail-finegrained-verify-models"
os.environ["KUBECONFIG"] = os.path.join(STATE, "kubeconfig")


def kubectl(*args, stdin=None, check=False):
    p = subprocess.run(["kubectl", *args], input=stdin, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"kubectl {' '.join(args)}: {p.stderr.strip()}")
    return p


def digest(name):
    return open(os.path.join(STATE, "digests", name)).read().strip()


def busybox():
    for line in open(os.path.join(FLAGSHIP, "airgap", "images.txt")):
        if line.startswith("docker.io/library/busybox:"):
            return line.strip()
    raise SystemExit("no busybox in the flagship's airgap/images.txt")


def placeholders():
    model = f"{REG}/models/model@{digest('model')}"
    subs = {
        "@BUSYBOX@": busybox(),
        "@MODEL@": model,
        "@MODEL_TAG@": f"{REG}/models/model:v1",
        "air-gapped-worker": "oscal-evidence-worker",
    }
    for plant in ("unsigned", "stranger", "unlicensed", "nobom", "mixed", "second", "expression", "concluded"):
        subs[f"@{plant.upper()}@"] = f"{REG}/models/plant-{plant}@{digest('plant-' + plant)}"
    return subs


def render(text, subs):
    for k, v in subs.items():
        text = text.replace(k, v)
    left = re.findall(r"@[A-Z_]+@", text)
    if left:
        raise SystemExit(f"placeholders left unfilled: {left}")
    return text


def refusal(out):
    """Which policy refused a request, and what it said, from the API server's answer."""
    m = re.search(r"ValidatingAdmissionPolicy '([^']+)' with binding '[^']*' denied request: (.*)", out)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.search(r'admission webhook "([^"]+)" denied the request: (.*)', out, re.S)
    if m:
        hook, msg = m.group(1), " ".join(m.group(2).split())
        return ("verify-models" if hook.endswith("-verify-models") else hook), msg
    m = re.search(r'failed calling webhook "([^"]+)"', out)
    if m:
        return f"unreachable webhook {m.group(1)}", " ".join(out.split())[:300]
    return None, " ".join(out.split())[:300]


def ask(manifest):
    p = kubectl("apply", "--dry-run=server", "-f", "-", stdin=manifest)
    out = (p.stdout + p.stderr).strip()
    if p.returncode == 0:
        return {"admitted": True, "refused_by": None, "message": out}
    by, msg = refusal(out)
    return {"admitted": False, "refused_by": by, "message": msg}


def header(path):
    lines = open(path).read().splitlines()
    says = " ".join(l[2:] for l in lines if l.startswith("# ") and not l.startswith("# expect:"))
    expect = next((l.split(":", 1)[1].strip() for l in lines if l.startswith("# expect:")), "")
    return says, expect.replace("registry.boundary.internal:5000", REG)


def hook_registered():
    p = kubectl("get", "validatingwebhookconfiguration", "kyverno-resource-validating-webhook-cfg",
                "-o", "jsonpath={.webhooks[*].name}")
    return p.returncode == 0 and HOOK in p.stdout.split()


def kyverno_away(subs):
    signed = render(open(os.path.join(FLAGSHIP, "tests/e2e/plants/model-signed.yaml")).read(), subs)
    result = {"test": "kyverno-away", "source": "tests/e2e/gameday.sh (step 1)",
              "flagship_says": "Kyverno's admission controller at zero replicas: the signed model is refused, "
                               "and admitted again once Kyverno is back",
              # With Kyverno's webhook configuration gone, the guard's parameter is
              # gone, and its binding refuses by parameterNotFoundAction: Deny, in
              # the API server's words rather than the policy's.
              "expect": "no params found for policy binding with `Deny` parameterNotFoundAction"}
    kubectl("-n", "kyverno", "scale", "deployment/kyverno-admission-controller", "--replicas=0", check=True)
    kubectl("-n", "kyverno", "wait", "pod", "-l", "app.kubernetes.io/component=admission-controller",
            "--for=delete", "--timeout=180s")
    for _ in range(15):
        if kubectl("get", "validatingwebhookconfiguration", "kyverno-resource-validating-webhook-cfg").returncode != 0:
            break
        time.sleep(2)
    gone = kubectl("get", "validatingwebhookconfiguration", "kyverno-resource-validating-webhook-cfg").returncode != 0
    if not gone:
        kubectl("delete", "validatingwebhookconfiguration", "kyverno-resource-validating-webhook-cfg", "--wait=true")
    result["webhook"] = "deleted by Kyverno on the way down" if gone else "kept by Kyverno; deleted by this test"
    result.update(ask(signed))
    kubectl("-n", "kyverno", "scale", "deployment/kyverno-admission-controller", "--replicas=1", check=True)
    kubectl("-n", "kyverno", "rollout", "status", "deployment/kyverno-admission-controller", "--timeout=300s")
    back = None
    for i in range(150):
        if hook_registered() and ask(signed)["admitted"]:
            back = i * 2
            break
        time.sleep(2)
    result["readmitted_after_seconds"] = back
    return result


def namespaces():
    """The flagship's namespaces the planted pods name, with its labels: inference
    (models verified, restricted Pod Security) and agents."""
    docs = []
    for path in ("manifests/namespaces.yaml", "manifests/inference/llama.yaml"):
        docs += [d for d in open(os.path.join(FLAGSHIP, path)).read().split("\n---\n")
                 if re.search(r"^kind: Namespace$", d, re.M)
                 and re.search(r"^  name: (agents|inference)$", d, re.M)]
    kubectl("apply", "-f", "-", stdin="\n---\n".join(docs), check=True)


def workloads(subs):
    template = open(os.path.join(ROOT, "workload/model-server.yaml")).read()
    servers = [("model-server", subs["@MODEL@"])]
    if PLANT == "audit:verify-models":
        servers.append(("unsigned-server", subs["@UNSIGNED@"]))
    applied = []
    for name, model in servers:
        doc = render(template.replace("@NAME@", name), {**subs, "@MODEL@": model})
        p = kubectl("apply", "-f", "-", stdin=doc)
        applied.append({"workload": f"inference/deployment/{name}", "model": model,
                        "applied": p.returncode == 0, "message": " ".join((p.stdout + p.stderr).split())})
    ordinary = render(open(os.path.join(FLAGSHIP, "tests/e2e/plants-frontier/ordinary-pod.yaml")).read(), subs)
    p = kubectl("apply", "-f", "-", stdin=ordinary)
    applied.append({"workload": "default/pod/ordinary-pod", "applied": p.returncode == 0,
                    "message": " ".join((p.stdout + p.stderr).split())})
    for w in applied:
        ns, kind, name = w["workload"].split("/")
        if kind == "deployment":
            r = kubectl("-n", ns, "rollout", "status", f"deployment/{name}", "--timeout=180s")
        else:
            r = kubectl("-n", ns, "wait", f"pod/{name}", "--for=condition=Ready", "--timeout=180s")
        w["running"] = r.returncode == 0
        if not w["running"]:
            ev = kubectl("-n", ns, "get", "events", "--sort-by=.lastTimestamp", "-o",
                         "jsonpath={range .items[*]}{.reason}: {.message}{'\\n'}{end}")
            w["events"] = ev.stdout.strip().splitlines()[-5:]
    return applied


def plants(subs):
    results = []
    files = sorted(glob.glob(os.path.join(FLAGSHIP, "tests/e2e/plants/*.yaml"))) + \
        sorted(glob.glob(os.path.join(FLAGSHIP, "tests/e2e/plants-frontier/*.yaml")))
    for path in files:
        says, expect = header(path)
        r = {"test": os.path.basename(path)[:-5], "source": os.path.relpath(path, FLAGSHIP),
             "flagship_says": says, "expect": expect}
        r.update(ask(render(open(path).read(), subs)))
        results.append(r)
    return results


def probe(out):
    """What Kyverno's report says about egress-node, a rule that applies only when a pod is
    created, for the ordinary pod: admitted, scheduled, broke nothing. egress-node is
    left out of the reports the evidence is built from (mapping/controls.yaml says why);
    here it is reported for a moment, after the reports are collected, so the reason is
    measured in every run rather than asserted, and then left out again."""
    label = "reports.kyverno.io/enabled"
    kubectl("label", "validatingadmissionpolicy", "egress-node", f"{label}=true", "--overwrite", check=True)
    kubectl("-n", "default", "annotate", "pod", "ordinary-pod", f"evidence/probe={int(time.time())}", "--overwrite")
    found = None
    for _ in range(36):
        reps = json.loads(kubectl("-n", "default", "get", "policyreports.wgpolicyk8s.io", "-o", "json").stdout or "{}")
        for rep in reps.get("items", []):
            if (rep.get("scope") or {}).get("name") != "ordinary-pod":
                continue
            found = next((r for r in rep.get("results") or [] if r.get("policy") == "egress-node"), None)
        if found:
            break
        time.sleep(5)
    kubectl("label", "validatingadmissionpolicy", "egress-node", f"{label}-", check=True)
    node = kubectl("-n", "default", "get", "pod", "ordinary-pod", "-o", "jsonpath={.spec.nodeName}").stdout
    record = {"policy": "egress-node", "pod": "default/ordinary-pod", "admitted": True, "node": node,
              "kyverno_result": (found or {}).get("result"), "kyverno_message": (found or {}).get("message"),
              "kyverno_process": ((found or {}).get("properties") or {}).get("process")}
    json.dump(record, open(out, "w"), indent=2)
    print(f"== probe: Kyverno's report for egress-node on the admitted, scheduled ordinary pod: "
          f"{record['kyverno_result'] or 'nothing within 3 minutes'}"
          + (f" ({record['kyverno_message']})" if found else ""))


def main():
    if sys.argv[1] == "--probe":
        probe(sys.argv[2])
        return
    out = sys.argv[1]
    subs = placeholders()
    namespaces()
    away = kyverno_away(subs)
    running = workloads(subs)
    planted = plants(subs)
    json.dump({"plant": PLANT or None, "workloads": running, "tests": [away] + planted},
              open(out, "w"), indent=2)
    refused = sum(1 for t in [away] + planted if not t["admitted"])
    print(f"== {len(planted) + 1} admission tests recorded ({refused} refused), "
          f"{sum(w.get('running', False) for w in running)} of {len(running)} workloads running")


if __name__ == "__main__":
    main()
