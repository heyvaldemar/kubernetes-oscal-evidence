#!/usr/bin/env bash
# models.sh - the model images the flagship's planted pods mount, made the
# way the flagship's scripts/model.sh makes them, and pushed into the run's
# registry.
#
# The control is a stand-in for model weights: a small file, signed with the
# operator's key and attested with an AI-BOM that scripts/mlbom.py (the
# flagship's, from the verified release) writes for Apache-2.0. Admission
# reads an image's signature and its AI-BOM, never the weights, so a small
# file exercises the same rules a 1 GB model does.
#
# The plants, as in the flagship: one nobody signed, one signed by a key the
# cluster does not trust, and ones signed by the operator whose AI-BOM is
# missing, declares a licence the site does not allow, or is shaped so that
# a looser rule would admit it; and a licence expression concluded to an
# allowed id, which must be admitted.
#
# Keys are made per run with no password and no transparency log, as the
# flagship's CI does: nothing inside its boundary can reach a log.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/.cache/run"
FLAGSHIP="$ROOT/.cache/flagship/src"
HOST="localhost:${REGISTRY_PORT:-5000}"
export SSL_CERT_FILE="$STATE/tls/bundle.pem" COSIGN_PASSWORD=""
say() { printf '== %s\n' "$*"; }
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
mkdir -p "$STATE/models" "$STATE/digests"

for who in operator stranger; do
  [ -s "$STATE/$who.key" ] || cosign generate-key-pair --output-key-prefix "$STATE/$who" >/dev/null 2>&1
done

sign() {  # sign <key> <name>
  cosign sign --key "$STATE/$1.key" --use-signing-config=false --tlog-upload=false --yes \
    "$HOST/models/$2@$(cat "$STATE/digests/$2")" >/dev/null 2>&1
}
attest() {  # attest <key> <name> <bom.json>
  cosign attest --key "$STATE/$1.key" --type cyclonedx --predicate "$3" \
    --use-signing-config=false --tlog-upload=false --yes "$HOST/models/$2@$(cat "$STATE/digests/$2")" >/dev/null 2>&1
}
bom() {  # bom <name> <licence> [jq edit]: the flagship's AI-BOM writer, then an edit
  python3 -I "$FLAGSHIP/scripts/mlbom.py" "$1" \
    "https://huggingface.co/plant/$1/resolve/0000000000000000000000000000000000000000/model.gguf" \
    "$(sha256 "$STATE/models/$1/model.gguf")" "$2" | jq "${3:-.}" >"$STATE/models/$1.mlbom.json"
}

for name in model plant-unsigned plant-stranger plant-unlicensed plant-nobom plant-mixed plant-second plant-expression plant-concluded; do
  mkdir -p "$STATE/models/$name"
  printf 'not a model: %s\n' "$name" >"$STATE/models/$name/model.gguf"
  python3 -I "$ROOT/scripts/oci.py" "$HOST" "models/$name:v1" "$STATE/models/$name/model.gguf" >"$STATE/digests/$name"
done

sign operator model
bom model Apache-2.0
attest operator model "$STATE/models/model.mlbom.json"

sign stranger plant-stranger
for name in plant-unlicensed plant-nobom plant-mixed plant-second plant-expression plant-concluded; do
  sign operator "$name"
done
bom plant-unlicensed GPL-3.0-only
bom plant-mixed Apache-2.0 '.components[0].licenses += [{"license": {"id": "CC-BY-NC-4.0"}}]'
bom plant-second Apache-2.0 '.components += [{"type": "machine-learning-model", "bom-ref": "second", "name": "plant-second-adapter"}]'
bom plant-expression Apache-2.0 '.components[0].licenses = [{"expression": "Apache-2.0 AND MIT"}]'
bom plant-concluded "Apache-2.0 OR CC-BY-NC-4.0"
for name in plant-unlicensed plant-mixed plant-second plant-expression plant-concluded; do
  attest operator "$name" "$STATE/models/$name.mlbom.json"
done
say "models: the control signed and attested (Apache-2.0); plants unsigned, stranger, unlicensed, nobom, mixed, second, expression, concluded"
