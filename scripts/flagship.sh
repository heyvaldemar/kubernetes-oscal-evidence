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
cosign verify-blob "$NAME.tar.gz" --bundle "$NAME.tar.gz.sigstore.json" \
  --certificate-identity "https://github.com/$REPO/.github/workflows/release-assets.yml@refs/tags/$TAG" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null 2>&1 \
  || { echo "cosign does not verify $NAME.tar.gz as signed by $REPO's release workflow on $TAG" >&2; exit 1; }
slsa-verifier verify-artifact "$NAME.tar.gz" --provenance-path "$NAME.intoto.jsonl" \
  --source-uri "github.com/$REPO" --source-tag "$TAG" >/dev/null 2>&1 \
  || { echo "slsa-verifier does not verify $NAME.tar.gz's provenance for $REPO at $TAG" >&2; exit 1; }
rm -rf "$OUT/src" && mkdir -p "$OUT/src"
tar -xzf "$NAME.tar.gz" -C "$OUT/src" --strip-components 1
say "$REPO $TAG: sha256 pinned, signature and provenance verified, unpacked into .cache/flagship/src"
