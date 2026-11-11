#!/usr/bin/env bash
# flagship.sh - fetch the release of the flagship that flagship.lock pins,
# verify it as a stranger would, and unpack it into .cache/flagship.
#
# Three checks, each of which refuses the archive on its own: the sha256
# pinned in flagship.lock; cosign verify-blob against the release's Sigstore
# bundle, with the exact identity of the flagship's release workflow on that
# tag; slsa-verifier against the release's provenance, for that tag. Nothing
# from the flagship is read before all three pass.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.cache/flagship"
say() { printf '== %s\n' "$*"; }
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
read -r REPO TAG SHA < <(grep -vE '^\s*(#|$)' "$ROOT/flagship.lock" | head -n 1)
NAME="${REPO#*/}-$TAG"
BASE="https://github.com/$REPO/releases/download/$TAG"

mkdir -p "$OUT/release"
for f in "$NAME.tar.gz" "$NAME.tar.gz.sigstore.json" "$NAME.intoto.jsonl"; do
  [ -s "$OUT/release/$f" ] || curl -fsSL --retry 3 -o "$OUT/release/$f" "$BASE/$f"
done
cd "$OUT/release"
got="$(sha256 "$NAME.tar.gz")"
[ "$got" = "$SHA" ] || { echo "$NAME.tar.gz is $got; flagship.lock pins $SHA" >&2; exit 1; }
# Each verifier's own last line goes with the refusal: a network fault on the
# way to Sigstore's TUF mirror and a signature that does not match read alike
# otherwise.
last() { printf '%s\n' "$1" | grep -v '^[[:space:]]*$' | tail -n 1; }
if ! out="$(cosign verify-blob "$NAME.tar.gz" --bundle "$NAME.tar.gz.sigstore.json" \
  --certificate-identity "https://github.com/$REPO/.github/workflows/release-assets.yml@refs/tags/$TAG" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com 2>&1)"; then
  echo "cosign does not verify $NAME.tar.gz as signed by $REPO's release workflow on $TAG: $(last "$out")" >&2; exit 1
fi
if ! out="$(slsa-verifier verify-artifact "$NAME.tar.gz" --provenance-path "$NAME.intoto.jsonl" \
  --source-uri "github.com/$REPO" --source-tag "$TAG" 2>&1)"; then
  echo "slsa-verifier does not verify $NAME.tar.gz's provenance for $REPO at $TAG: $(last "$out")" >&2; exit 1
fi
rm -rf "$OUT/src" && mkdir -p "$OUT/src"
tar -xzf "$NAME.tar.gz" -C "$OUT/src" --strip-components 1
say "$REPO $TAG: sha256 pinned, signature and provenance verified, unpacked into .cache/flagship/src"
