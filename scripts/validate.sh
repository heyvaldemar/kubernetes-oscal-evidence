#!/usr/bin/env bash
# validate.sh EVIDENCE_DIR - compliance-trestle's own validator over every OSCAL
# document of a run: the component definition, C2P's assessment plans, and
# the assessment results, in a trestle workspace made for the purpose.
# Any document trestle refuses fails this script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EVIDENCE="$(cd "$1" && pwd)"
WS="$(mktemp -d)"
trap 'rm -rf "$WS"' EXIT
cd "$WS"
trestle init >/dev/null
mkdir -p component-definitions/admission
cp "$ROOT/oscal/component-definition.json" component-definitions/admission/component-definition.json
for f in "$EVIDENCE"/c2p/assessment-plan-*.json; do
  n="$(basename "$f" .json)"; mkdir -p "assessment-plans/$n"; cp "$f" "assessment-plans/$n/assessment-plan.json"
done
for f in "$EVIDENCE"/assessment-results-*.json; do
  n="$(basename "$f" .json)"; mkdir -p "assessment-results/$n"; cp "$f" "assessment-results/$n/assessment-results.json"
done
trestle validate -a >"$WS/validate.log" 2>&1 || { cat "$WS/validate.log" >&2; exit 1; }
valid="$(grep -c '^VALID' "$WS/validate.log" || true)"
echo "== trestle validate: $valid documents valid (component definition, assessment plans, assessment results)"
