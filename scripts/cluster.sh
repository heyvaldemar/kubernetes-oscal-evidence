#!/usr/bin/env bash
# cluster.sh <up|down> - the cluster the flagship's policies are brought up on.
#
#   up    kind with the flagship's two nodes (kind/cluster.yaml), and zot, a
#         registry that speaks only TLS, on kind's network as
#         registry.boundary.internal:5000, the name the flagship's policies
#         expect. Its certificate comes from a CA made for this run; the
#         nodes' containerd and, later, Kyverno trust that CA. The host
#         reaches the same registry as localhost:$REGISTRY_PORT.
#   down  delete both.
#
# This is not the flagship's boundary: nothing here closes the network. The
# policies decide the same way with the network open, and that is all this
# repository measures (README, "What it does not prove").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT/.cache/run"
CLUSTER=oscal-evidence
NAME=registry.boundary.internal
REGISTRY=oscal-evidence-registry
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
# The flagship's registry image, from airgap/registry.ref at the pinned release.
ZOT="$(tr -d '[:space:]' <"$ROOT/.cache/flagship/src/airgap/registry.ref")"
say() { printf '== %s\n' "$*"; }

case "${1:-}" in
  up)
    mkdir -p "$STATE/tls"
    if [ ! -s "$STATE/tls/ca.crt" ]; then
      # Key identifiers and usages written out: Python 3.13 and later verify
      # strictly (VERIFY_X509_STRICT) and refuse a chain without them.
      printf '%s\n' 'basicConstraints=critical,CA:TRUE' 'keyUsage=critical,keyCertSign,cRLSign' \
        'subjectKeyIdentifier=hash' >"$STATE/tls/ca.ext"
      openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=oscal-evidence run CA" \
        -keyout "$STATE/tls/ca.key" -out "$STATE/tls/ca.csr" 2>/dev/null
      openssl x509 -req -in "$STATE/tls/ca.csr" -signkey "$STATE/tls/ca.key" -days 2 \
        -extfile "$STATE/tls/ca.ext" -out "$STATE/tls/ca.crt" 2>/dev/null
      openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$NAME" \
        -keyout "$STATE/tls/tls.key" -out "$STATE/tls/tls.csr" 2>/dev/null
      printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'keyUsage=critical,digitalSignature' 'extendedKeyUsage=serverAuth' \
        'subjectKeyIdentifier=hash' 'authorityKeyIdentifier=keyid' \
        "subjectAltName=DNS:$NAME,DNS:localhost,IP:127.0.0.1" >"$STATE/tls/san.ext"
      openssl x509 -req -in "$STATE/tls/tls.csr" -CA "$STATE/tls/ca.crt" -CAkey "$STATE/tls/ca.key" -CAcreateserial \
        -days 2 -extfile "$STATE/tls/san.ext" -out "$STATE/tls/tls.crt" 2>/dev/null
      chmod 644 "$STATE/tls/tls.key"  # read by zot's non-root user inside its container
    fi
    # The trust bundle the host's tools read: the system's CAs and this one.
    sys=/etc/ssl/certs/ca-certificates.crt; [ -f "$sys" ] || sys=/etc/ssl/cert.pem
    cat "$sys" "$STATE/tls/ca.crt" >"$STATE/tls/bundle.pem"

    kind get clusters 2>/dev/null | grep -qx "$CLUSTER" \
      || kind create cluster --config "$ROOT/kind/cluster.yaml" --wait 120s >/dev/null
    kind export kubeconfig --name "$CLUSTER" --kubeconfig "$STATE/kubeconfig" >/dev/null 2>&1

    cat >"$STATE/zot.json" <<JSON
{
  "distSpecVersion": "1.1.1",
  "storage": {"rootDirectory": "/var/lib/registry", "dedupe": false, "gc": false},
  "http": {"address": "0.0.0.0", "port": "5000", "tls": {"cert": "/etc/zot/tls/tls.crt", "key": "/etc/zot/tls/tls.key"}},
  "log": {"level": "warn"}
}
JSON
    docker rm -f "$REGISTRY" >/dev/null 2>&1 || true
    docker run -d --name "$REGISTRY" --network kind --network-alias "$NAME" \
      -p "127.0.0.1:$REGISTRY_PORT:5000" \
      -v "$STATE/zot.json:/etc/zot/config.json:ro" -v "$STATE/tls:/etc/zot/tls:ro" \
      "$ZOT" serve /etc/zot/config.json >/dev/null
    for _ in $(seq 1 30); do
      curl -fsS --cacert "$STATE/tls/ca.crt" "https://localhost:$REGISTRY_PORT/v2/" >/dev/null 2>&1 && break
      sleep 1
    done
    curl -fsS --cacert "$STATE/tls/ca.crt" "https://localhost:$REGISTRY_PORT/v2/" >/dev/null

    # containerd on each node pulls from the registry over TLS with the run's CA.
    for node in $(kind get nodes --name "$CLUSTER"); do
      docker exec "$node" mkdir -p "/etc/containerd/certs.d/$NAME:5000"
      docker exec -i "$node" tee "/etc/containerd/certs.d/$NAME:5000/ca.crt" <"$STATE/tls/ca.crt" >/dev/null
      printf 'server = "https://%s:5000"\n\n[host."https://%s:5000"]\n  capabilities = ["pull", "resolve"]\n  ca = "/etc/containerd/certs.d/%s:5000/ca.crt"\n' \
        "$NAME" "$NAME" "$NAME" | docker exec -i "$node" tee "/etc/containerd/certs.d/$NAME:5000/hosts.toml" >/dev/null
    done
    say "kind cluster $CLUSTER ($(kind get nodes --name "$CLUSTER" | wc -l | tr -d ' ') nodes) and zot as https://$NAME:5000 (localhost:$REGISTRY_PORT from the host)"
    ;;
  down)
    docker rm -f "$REGISTRY" >/dev/null 2>&1 || true
    kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true
    say "cluster $CLUSTER and its registry deleted"
    ;;
  *) echo "usage: cluster.sh <up|down>" >&2; exit 2 ;;
esac
