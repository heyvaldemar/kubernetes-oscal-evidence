#!/usr/bin/env bash
# admission.sh - Kyverno and the flagship's admission policies, as the
# flagship's own scripts/admission.sh installs them: the chart its
# admission/charts.lock pins, checked against that sha256, with its images
# (admission/kyverno-images.yaml) and values, the run's CA added to Kyverno's
# trust; then each policy from admission/, the signature policy with the
# operator's public key written in.
#
# carried-images takes a ConfigMap of the digests the flagship's signed bundle
# carried. There is no bundle here, so the list is what the bundle would hold
# for these pods: Kyverno's images, busybox (airgap/images.txt) and the
# models this run pushed. The planted image and volume that were never
# carried stay off it.
#
# Kyverno writes PolicyReports for these policies only when told to, and the
# flagship does not tell it: it relies on refusals, not reports. Three
# settings here change what Kyverno reports and nothing the API server
# decides (README, "What Kyverno's reports needed"):
#   - each native policy Kyverno is to report on carries the label
#     reports.kyverno.io/enabled=true; egress-node does not (its posture
#     cannot be judged from stored pods, mapping/controls.yaml);
#   - verify-models runs Kyverno's background scan (evaluation.background
#     true; the flagship ships false), because Kyverno 1.19 writes no
#     admission report for a CEL policy whose actions include Deny, even
#     for a pod it admits;
#   - Kyverno's reports controller may read webhook configurations, which
#     is the parameter of models-need-kyverno.
REPORTED_VAPS="carried-images model-volumes models-need-kyverno"
#
# PLANT changes what is installed, to show that the evidence and the gate
# catch it (README, "The plants"):
#   remove:<policy>   that policy is never applied
#   audit:verify-models  the signature policy records instead of refusing
#                     (validationActions [Audit]), so an unsigned model is
#                     admitted and runs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/.cache/run"
FLAGSHIP="$ROOT/.cache/flagship/src"
# Kyverno 1.20.0-rc.3 before GA (branch kyverno-1.20-rc only): the chart and
# image pins come from kyverno-rc/, copied from the flagship's branch of the
# same name; the policies and values are still the flagship release's.
PINS="$ROOT/kyverno-rc"
PLANT="${PLANT:-}"
export KUBECONFIG="$STATE/kubeconfig"
say() { printf '== %s\n' "$*"; }
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
read -r _ VERSION REPO SHA < <(grep -E '^kyverno ' "$PINS/charts.lock")
CHART="$STATE/charts/kyverno-$VERSION.tgz"

wanted() { [ "$PLANT" != "remove:$1" ]; }

render_verify_models() {
  python3 -I - "$FLAGSHIP/admission/verify-models.yaml" "$STATE/operator.pub" "$PLANT" <<'PY'
import sys
policy, key, plant = open(sys.argv[1]).read(), open(sys.argv[2]).read().strip(), sys.argv[3]
policy = policy.replace("@OPERATOR_KEY@", key.replace("\n", "\n            "))
background = "  evaluation:\n    background:\n      enabled: false\n"
assert background in policy, "verify-models no longer sets evaluation.background as this script expects"
policy = policy.replace(background, background.replace("false", "true"), 1)
if plant == "audit:verify-models":
    assert "  validationActions: [Deny]\n" in policy
    policy = policy.replace("  validationActions: [Deny]\n", "  validationActions: [Audit]\n", 1)
print(policy)
PY
}

mkdir -p "$STATE/charts"
[ -s "$CHART" ] || helm pull kyverno --repo "$REPO" --version "$VERSION" -d "$STATE/charts" >/dev/null
[ "$(sha256 "$CHART")" = "$SHA" ] || { echo "kyverno-$VERSION.tgz is not the archive the flagship's charts.lock pins" >&2; exit 1; }
helm upgrade --install kyverno "$CHART" --namespace kyverno --create-namespace --wait --timeout 10m \
  -f "$PINS/kyverno-images.yaml" -f "$FLAGSHIP/admission/kyverno-values.yaml" \
  --set-file "global.caCertificates.data=$STATE/tls/ca.crt" >/dev/null
kubectl -n kyverno rollout status deployment/kyverno-admission-controller --timeout=300s >/dev/null
for _ in $(seq 1 60); do
  render_verify_models | kubectl apply --dry-run=server -f - >/dev/null 2>&1 && break
  sleep 5
done
say "kyverno $VERSION from the chart the flagship pins, its images by digest"

# What the bundle would carry for these pods.
{
  grep -Eo 'sha256:[0-9a-f]{64}' "$PINS/kyverno-images.yaml"
  grep -E '^docker\.io/library/busybox:' "$FLAGSHIP/airgap/images.txt" | grep -Eo 'sha256:[0-9a-f]{64}'
  cat "$STATE"/digests/*
} | sort -u | tr '\n' ' ' | sed 's/ $//' >"$STATE/carried-digests.txt"
kubectl -n kube-system create configmap carried-images --from-file=digests="$STATE/carried-digests.txt" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

kubectl apply -f - >/dev/null <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kyverno:reports-controller:webhook-configurations
  labels:
    rbac.kyverno.io/aggregate-to-reports-controller: "true"
rules:
  - apiGroups: [admissionregistration.k8s.io]
    resources: [validatingwebhookconfigurations]
    verbs: [get, list, watch]
YAML

applied=()
if wanted carried-images; then kubectl apply -f "$FLAGSHIP/admission/carried-images.yaml" >/dev/null; applied+=(carried-images); fi
if wanted model-volumes; then kubectl apply -f "$FLAGSHIP/admission/model-volumes.yaml" >/dev/null; applied+=(model-volumes); fi
if wanted egress-node; then kubectl apply -f "$FLAGSHIP/admission/egress-node.yaml" >/dev/null; applied+=(egress-node); fi
if wanted verify-models; then
  render_verify_models | kubectl apply -f - >/dev/null
  for _ in $(seq 1 60); do
    [ "$(kubectl get imagevalidatingpolicy verify-models -o jsonpath='{.status.conditionStatus.ready}' 2>/dev/null)" = true ] && break
    sleep 2
  done
  applied+=(verify-models)
fi
if wanted models-need-kyverno; then
  # The guard reads Kyverno's webhook for verify-models, and goes on once it
  # is registered, as in the flagship. Without verify-models it never is,
  # and the guard is applied anyway: it then refuses every model, which is
  # what it is for.
  hook=ivpol.validate.kyverno.svc-fail-finegrained-verify-models
  if wanted verify-models; then
    for _ in $(seq 1 60); do
      kubectl get validatingwebhookconfiguration kyverno-resource-validating-webhook-cfg -o jsonpath='{.webhooks[*].name}' 2>/dev/null \
        | tr ' ' '\n' | grep -qx "$hook" && break
      sleep 2
    done
  fi
  kubectl apply -f "$FLAGSHIP/admission/kyverno-guard.yaml" >/dev/null
  applied+=(models-need-kyverno)
fi
for p in $REPORTED_VAPS; do
  kubectl get validatingadmissionpolicy "$p" >/dev/null 2>&1 \
    && kubectl label validatingadmissionpolicy "$p" reports.kyverno.io/enabled=true --overwrite >/dev/null
done
printf '%s\n' "${applied[@]}" >"$STATE/applied-policies.txt"
say "policies applied: ${applied[*]}${PLANT:+ (plant: $PLANT)}; carried-images holds $(wc -w <"$STATE/carried-digests.txt" | tr -d ' ') digests"
