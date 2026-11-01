#!/usr/bin/env bash
# catalogs.sh - NIST's OSCAL catalogs and the control-to-test matrix that
# catalogs.lock pins, into .cache/catalogs, each refused unless its sha256 is
# the pinned one.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.cache/catalogs"
sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
mkdir -p "$OUT"
while read -r file url sum; do
  case "$file" in ''|'#'*) continue ;; esac
  [ -s "$OUT/$file" ] && [ "$(sha256 "$OUT/$file")" = "$sum" ] && continue
  curl -fsSL --retry 3 -o "$OUT/$file" "$url"
  got="$(sha256 "$OUT/$file")"
  [ "$got" = "$sum" ] || { echo "$file is $got; catalogs.lock pins $sum" >&2; rm -f "$OUT/$file"; exit 1; }
done <"$ROOT/catalogs.lock"
echo "== catalogs.lock, every file checked: $(awk '!/^#/ && NF {print $1}' "$ROOT/catalogs.lock" | tr '\n' ' ')"
