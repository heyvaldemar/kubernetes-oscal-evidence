#!/usr/bin/env bash
# run.sh - the whole run, as CI runs it, on this machine: the flagship's
# policies on kind, its planted pods, Kyverno's reports, C2P and trestle,
# and the gate. Evidence lands in .cache/run/evidence. The steps are the
# scripts in scripts/; this is the order they run in.
#
#   PLANT=remove:<policy> | audit:verify-models | phantom-mapping  break it on purpose
#   KEEP=1  leave the cluster up afterwards; bash scripts/cluster.sh down is the teardown
#
# CI creates the kind cluster in a step of its own first; scripts/cluster.sh
# finds it and keeps it, and creates it when it is not there.
#
# Needs docker, curl, jq, openssl and Python 3.11 or later with
# requirements.lock installed (python3 -m pip install --require-hashes -r requirements.lock).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="$ROOT/.cache/run"
PLANT="${PLANT:-}"
export PLANT
BIN="$(bash "$ROOT/scripts/install-tools.sh")"
export PATH="$BIN:$PATH"
cd "$ROOT"
mkdir -p "$STATE"

bash scripts/flagship.sh
bash scripts/catalogs.sh
export MAPPING="$ROOT/mapping/controls.yaml" COMPONENT_DEFINITION="$ROOT/oscal/component-definition.json"
if [ "$PLANT" = phantom-mapping ]; then
  # The mapping names verify-model-signatures, a policy the flagship does not have.
  sed -E 's/verify-models([^.]|$)/verify-model-signatures\1/g' mapping/controls.yaml >"$STATE/mapping.yaml"
  if python3 scripts/component.py --mapping "$STATE/mapping.yaml" --out "$STATE/component-definition.json"; then
    echo "the mapping check let a policy that does not exist through" >&2; exit 1
  fi
  echo "== the mapping check refused it; building it anyway, to see the run refuse it too"
  python3 scripts/component.py --mapping "$STATE/mapping.yaml" --out "$STATE/component-definition.json" --unchecked
  export MAPPING="$STATE/mapping.yaml" COMPONENT_DEFINITION="$STATE/component-definition.json"
else
  python3 scripts/component.py --check
fi

bash scripts/cluster.sh up
bash scripts/models.sh
bash scripts/admission.sh
python3 scripts/tests.py "$STATE/admission-tests.json"
python3 scripts/collect.py "$STATE/reports"
python3 scripts/tests.py --probe "$STATE/reporting-probe.json"
rm -rf "$STATE/evidence"
python3 scripts/evidence.py "$STATE/evidence"
cp "$STATE/admission-tests.json" "$STATE/reporting-probe.json" "$STATE/evidence/"
cp -R "$STATE/reports/raw" "$STATE/evidence/policyreports"
bash scripts/validate.sh "$STATE/evidence"
[ -n "${KEEP:-}" ] || bash scripts/cluster.sh down
python3 scripts/gate.py "$STATE/evidence" ${PLANT:+--plant "$PLANT"}
