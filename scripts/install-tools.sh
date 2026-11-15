#!/usr/bin/env bash
# install-tools.sh [bin-dir] - install the tools in tools.lock for this
# platform, each checked against its pinned sha256, and C2P in an
# environment of its own; prints the directory to put on PATH. What is
# already installed with the right hashes is kept.
#
# C2P, the Python implementation, goes into .cache/c2p: a virtual
# environment with compliance-trestle 3.x, every file by hash
# (c2p/requirements.lock), beside the trestle 5.x the evidence is written
# with (docs/decisions/0005). Its plugins are not in its wheel; the five
# files the run imports come from the commit OSCAL Compass's signed v1.0.0
# tag names, each checked against c2p/plugins.lock. PYTHON names the
# interpreter for that environment (python3 when unset).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${1:-$ROOT/.cache/bin}"
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=linux-amd64 ;;
  Darwin-arm64) platform=darwin-arm64 ;;
  *) echo "no pins for $(uname -s)-$(uname -m); add them to tools.lock" >&2; exit 1 ;;
esac
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

mkdir -p "$BIN/.downloads"
while read -r name version plat url member sum; do
  case "$name" in ''|'#'*) continue ;; esac
  [ "$plat" = "$platform" ] || continue
  dest="$BIN/$name"
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

C2P="$ROOT/.cache/c2p"
C2P_COMMIT=4023a29aaebc76d548143599d323f4f48fb9c923
want="$(sha256 "$ROOT/c2p/requirements.lock") $(sha256 "$ROOT/c2p/plugins.lock")"
if [ "$(cat "$C2P/.installed" 2>/dev/null)" != "$want" ]; then
  rm -rf "${C2P:?}"
  "${PYTHON:-python3}" -m venv "$C2P"
  "$C2P/bin/pip" install --quiet --disable-pip-version-check --require-hashes --no-deps \
    -r "$ROOT/c2p/requirements.lock" >&2
  while read -r path sum; do
    case "$path" in ''|'#'*) continue ;; esac
    mkdir -p "$C2P/src/$(dirname "$path")"
    curl -fsSL --retry 3 -o "$C2P/src/$path" \
      "https://raw.githubusercontent.com/oscal-compass/compliance-to-policy/$C2P_COMMIT/$path"
    got="$(sha256 "$C2P/src/$path")"
    if [ "$got" != "$sum" ]; then
      echo "C2P's $path: sha256 $got, pinned $sum. Not installing." >&2
      rm -rf "${C2P:?}"
      exit 1
    fi
  done <"$ROOT/c2p/plugins.lock"
  echo "$want" >"$C2P/.installed"
  echo "installed C2P 1.0.0 and its plugins in .cache/c2p" >&2
fi
echo "$BIN"
