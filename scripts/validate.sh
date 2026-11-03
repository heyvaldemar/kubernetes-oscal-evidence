#!/usr/bin/env bash
# validate.sh [check...] - the static checks, without a cluster:
#
#   component  oscal/component-definition.json is what mapping/controls.yaml
#              gives, and names no policy, planted pod, control or matrix row
#              that does not exist (scripts/component.py --check)
#   nodes      kind/cluster.yaml has the nodes of the flagship's
#              kind/frontier.yaml
#   workload   manifests/model-server.yaml is shaped like the flagship's model
#              server: its namespace, its pod and container security
#              settings, the model mounted read-only from an image volume,
#              and the busybox the flagship carries
#   images     every container image this repository names is referenced by
#              digest
#   trestle    compliance-trestle validates the component definition and the
#              evidence the gate's tests read (tests/fixtures/evidence)
#   gate       the gate's tests (tests/test_evidence.py)
#   mutations  each rule of the gate switched off in turn, and the test named
#              for it fails (scripts/mutate.py, tests/plants.tsv)
#
# validate.sh EVIDENCE_DIR - compliance-trestle's validator over one run's
# OSCAL documents: the component definition, C2P's assessment plans and the
# assessment results. tests/e2e/run.sh calls it so, and so does anyone
# checking a release's evidence (README, "Check it yourself").
#
# With no arguments every static check runs. The flagship's release and
# NIST's catalogs must be in .cache first (scripts/flagship.sh,
# scripts/catalogs.sh), and Python with requirements.lock on PATH.
# tests/static/plants.tsv shows each check the violation it exists for
# (tests/static/plant_violations.py). The check_* functions are called by
# name from the loop at the bottom.
# shellcheck disable=SC2329
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLAGSHIP=.cache/flagship/src

# trestle_validate DIR [plans]: the component definition, and DIR's
# assessment results and, with "plans", C2P's assessment plans in DIR/c2p,
# in a trestle workspace made for the purpose. Any document trestle refuses
# fails it, and so does a directory with no assessment results.
trestle_validate() {
  local evidence ws f n rc
  evidence="$(cd "$1" && pwd)" || return 1
  ws="$(mktemp -d)" || return 1
  (
    cd "$ws" || exit 1
    trestle init >/dev/null || exit 1
    mkdir -p component-definitions/admission
    cp "$ROOT/oscal/component-definition.json" component-definitions/admission/component-definition.json || exit 1
    if [ "${2:-}" = plans ]; then
      for f in "$evidence"/c2p/assessment-plan-*.json; do
        [ -e "$f" ] || { echo "no assessment plans in $evidence/c2p"; exit 1; }
        n="$(basename "$f" .json)"; mkdir -p "assessment-plans/$n"; cp "$f" "assessment-plans/$n/assessment-plan.json" || exit 1
      done
    fi
    for f in "$evidence"/assessment-results-*.json; do
      [ -e "$f" ] || { echo "no assessment results in $evidence"; exit 1; }
      n="$(basename "$f" .json)"; mkdir -p "assessment-results/$n"; cp "$f" "assessment-results/$n/assessment-results.json" || exit 1
    done
    trestle validate -a >validate.log 2>&1 || { cat validate.log >&2; exit 1; }
    echo "== trestle validate: $(grep -c '^VALID' validate.log) documents valid" \
      "(component definition, $( [ "${2:-}" = plans ] && echo 'assessment plans, ')assessment results)"
  )
  rc=$?
  rm -rf "$ws"
  return "$rc"
}

check_component() { python3 scripts/component.py --check; }

check_nodes() {
  nodes() { sed -n '/^nodes:/,$p' "$1" | grep -v '^[[:space:]]*#'; }
  diff <(nodes kind/cluster.yaml) <(nodes "$FLAGSHIP/kind/frontier.yaml") || return 1
  echo "kind/cluster.yaml has the nodes of the flagship's kind/frontier.yaml"
}

check_workload() {
  python3 - "$FLAGSHIP" <<'PY'
import re, sys
from ruamel.yaml import YAML

flagship = sys.argv[1]


def docs(path):
    # The placeholders (@NAME@, @MODEL@) are filled in at run time and are
    # not YAML; the same stand-in in both files compares them as equal.
    text = re.sub(r"@[A-Z_]+@", "PLACEHOLDER", open(path).read())
    return [d for d in YAML(typ="safe").load_all(text) if d]


ours = docs("manifests/model-server.yaml")[0]
theirs = next(d for d in docs(f"{flagship}/manifests/inference/llama.yaml")
              if d.get("kind") == "Deployment" and d["metadata"].get("namespace") == "inference")
busybox = next(l.strip() for l in open(f"{flagship}/airgap/images.txt") if l.startswith("docker.io/library/busybox:"))
o, t = ours["spec"]["template"]["spec"], theirs["spec"]["template"]["spec"]
oc, tc = o["containers"][0], t["containers"][0]
model = lambda spec: next(v for v in spec["volumes"] if v["name"] == "model")
mount = lambda c: next((m for m in c.get("volumeMounts", []) if m["name"] == "model"), None)
bad = []
for what, a, b in [
    ("namespace", ours["metadata"]["namespace"], theirs["metadata"]["namespace"]),
    ("automountServiceAccountToken", o.get("automountServiceAccountToken"), t.get("automountServiceAccountToken")),
    ("the pod's securityContext", o.get("securityContext"), t.get("securityContext")),
    ("the container's securityContext", oc.get("securityContext"), tc.get("securityContext")),
    ("the model's mount", mount(oc), mount(tc)),
    ("the model's volume", model(o), model(t)),
]:
    if a != b:
        bad.append(f"{what}: {a!r}, the flagship's model server has {b!r}")
if oc["image"] != busybox:
    bad.append(f"the server's image is {oc['image']}; the flagship carries {busybox}")
print("\n".join(bad) or "manifests/model-server.yaml is shaped like the flagship's model server, on the busybox it carries")
sys.exit(1 if bad else 0)
PY
}

check_images() {
  python3 - <<'PY'
import glob, re, sys
bad = []
for path in sorted(glob.glob("manifests/**/*.yaml", recursive=True)) + ["kind/cluster.yaml"]:
    for n, line in enumerate(open(path), 1):
        m = re.match(r"\s*-?\s*image:\s*(\S+)", line)
        if m and "@sha256:" not in m.group(1):
            bad.append(f"{path}:{n}: {m.group(1)}")
for n, line in enumerate(open("ci-images.pins"), 1):
    m = re.match(r"^([A-Z0-9_]+_IMAGE)=(\S*)$", line)
    if m and "@sha256:" not in m.group(2):
        bad.append(f"ci-images.pins:{n}: {m.group(1)}={m.group(2)}")
print("images without a digest:\n" + "\n".join(bad) if bad else "every container image is referenced by digest")
sys.exit(1 if bad else 0)
PY
}

check_trestle() { trestle_validate tests/fixtures/evidence; }

check_gate() {
  python3 -m unittest discover -s tests 2>&1 | tail -3
  return "${PIPESTATUS[0]}"
}

check_mutations() {
  python3 scripts/mutate.py 2>&1 | grep -E '^(MISSED|PLANT DOES NOT APPLY|==)'
  return "${PIPESTATUS[0]}"
}

# One argument that names no check and is a directory: a run's evidence.
if [ $# -eq 1 ] && ! declare -F "check_$1" >/dev/null && [ -d "$1" ]; then
  dir="$(cd "$1" && pwd)"
  cd "$ROOT" || exit 1
  trestle_validate "$dir" plans
  exit $?
fi

cd "$ROOT" || exit 1
if [ ! -d "$FLAGSHIP" ] || [ ! -d .cache/catalogs ]; then
  echo "the flagship's release and NIST's catalogs are not in .cache: run scripts/flagship.sh and scripts/catalogs.sh first" >&2
  exit 2
fi
checks=("$@")
[ ${#checks[@]} -eq 0 ] && checks=(component nodes workload images trestle gate mutations)
failed=0
for c in "${checks[@]}"; do
  if ! declare -F "check_$c" >/dev/null; then echo "-- $c: no such check"; failed=1; continue; fi
  if "check_$c"; then echo "-- $c: ok"; else echo "-- $c: FAILED"; failed=1; fi
done
exit "$failed"
