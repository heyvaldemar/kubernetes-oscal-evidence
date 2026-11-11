#!/usr/bin/env bash
# install-tools.sh [bin-dir] - install the tools in tools.lock for this
# platform, each checked against its pinned sha256, and prints the directory
# to put on PATH. Already-installed tools with the right hash are kept.
#
# C2P's pins are also traced to its publisher: the release's checksums file
# must carry a valid cosign signature from OSCAL Compass's release workflow,
# and must list every C2P hash tools.lock pins.
#
# C2P runs its Kyverno plugin only if the plugin's manifest names the
# binary's sha256. The manifest in the v2.0.0-rc.1 tarballs names
# 833ce6b7..., which is neither the linux-amd64 nor the darwin-arm64 binary
# beside it, and c2pcli then stops with "checksums did not match". So the
# manifest is written here, from the binary this script has just checked.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${1:-$ROOT/.cache/bin}"
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=linux-amd64 ;;
  Darwin-arm64) platform=darwin-arm64 ;;
  *) echo "no pins for $(uname -s)-$(uname -m); add them to tools.lock" >&2; exit 1 ;;
esac
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

C2P_RELEASE=https://github.com/oscal-compass/compliance-to-policy-go/releases/download/v2.0.0-rc.1
C2P_CHECKSUMS=compliance-to-policy-go_2.0.0-rc.1_checksums.txt
# The release was signed by a run of this workflow on main, not on the tag;
# the certificate says so, and this is the identity it carries.
C2P_SIGNER=https://github.com/oscal-compass/compliance-to-policy-go/.github/workflows/goreleaser-workflow.yml@refs/heads/main

mkdir -p "$BIN/.downloads" "$BIN/c2p-plugins"
while read -r name version plat url member sum; do
  case "$name" in ''|'#'*) continue ;; esac
  [ "$plat" = "$platform" ] || continue
  dest="$BIN/$name"; [ "$name" = kyverno-plugin ] && dest="$BIN/c2p-plugins/$name"
  marker="$BIN/.downloads/$name-$version-$plat.sha256"
  if [ -x "$dest" ] && [ "$(cat "$marker" 2>/dev/null)" = "$sum" ]; then
    continue
  fi
  file="$BIN/.downloads/$(basename "$url")"
  curl -fsSL --retry 3 -o "$file" "$url"
  got="$(sha256 "$file")"
  if [ "$got" != "$sum" ]; then
    echo "$name $version: sha256 $got, pinned $sum. Not installing." >&2
    exit 1
  fi
  case "$url" in
    *.tar.gz) tar -xzf "$file" -C "$BIN/.downloads" "$member" && mv -f "$BIN/.downloads/$member" "$dest" ;;
    *) cp -f "$file" "$dest" ;;
  esac
  chmod +x "$dest"
  echo "$sum" >"$marker"
  echo "installed $name $version" >&2
done <"$ROOT/tools.lock"

# C2P's checksums file, its signature and certificate, verified with the
# cosign just installed; then every C2P pin must be a line of it.
(
  cd "$BIN/.downloads"
  for f in "$C2P_CHECKSUMS" "$C2P_CHECKSUMS.sig" "$C2P_CHECKSUMS.pem"; do
    [ -s "$f" ] || curl -fsSL --retry 3 -o "$f" "$C2P_RELEASE/$f"
  done
  # cosign's own last line goes with the refusal, so a network fault does not
  # read as a bad signature.
  if ! out="$("$BIN/cosign" verify-blob "$C2P_CHECKSUMS" --signature "$C2P_CHECKSUMS.sig" --certificate "$C2P_CHECKSUMS.pem" \
    --certificate-identity "$C2P_SIGNER" --certificate-oidc-issuer https://token.actions.githubusercontent.com 2>&1)"; then
    echo "C2P's checksums file does not verify as signed by $C2P_SIGNER: $(printf '%s\n' "$out" | grep -v '^[[:space:]]*$' | tail -n 1)" >&2; exit 1
  fi
  while read -r name _ _ url _ sum; do
    case "$name" in c2pcli|kyverno-plugin) ;; *) continue ;; esac
    awk -v s="$sum" -v f="$(basename "$url")" '$1 == s && $2 == f { found = 1 } END { exit !found }' "$C2P_CHECKSUMS" \
      || { echo "$(basename "$url") $sum is not in C2P's signed checksums file" >&2; exit 1; }
  done <"$ROOT/tools.lock"
)

plugin_sum="$(sha256 "$BIN/c2p-plugins/kyverno-plugin")"
cat >"$BIN/c2p-plugins/c2p-kyverno-manifest.json" <<EOF
{
  "metadata": {"id": "kyverno", "description": "Kyverno PVP Plugin", "version": "0.0.1", "types": ["pvp"]},
  "executablePath": "kyverno-plugin",
  "sha256": "$plugin_sum",
  "configuration": [
    {"name": "policy-dir", "description": "A directory where kyverno policies are located.", "required": true},
    {"name": "policy-results-dir", "description": "A directory where policy results are located", "required": true},
    {"name": "temp-dir", "description": "A temporary directory for policies", "required": true},
    {"name": "output-dir", "description": "The output directory for policies", "required": false, "default": "."}
  ]
}
EOF
echo "$BIN"
