#!/usr/bin/env python3
"""oci.py REGISTRY REPO:TAG FILE - push FILE as /model.gguf in a FROM-scratch image.

The model images the planted pods mount: an OCI image index with one
manifest for linux/amd64 and one for linux/arm64, both pointing at the same
single layer, so a kind node of either kind can mount it. The flagship builds
its model images with BuildKit from models/Dockerfile (FROM scratch, COPY
model.gguf); this writes the same shape with the standard library, so the
run needs no image builder.

Deterministic: the tar entry has mtime 0 and owner 0, and the gzip header has
no time, so the same file gives the same digest on any machine.

Prints the index digest. REGISTRY is host:port and is reached over TLS with
the CA bundle in SSL_CERT_FILE.
"""
import gzip
import hashlib
import io
import json
import os
import ssl
import sys
import tarfile
import urllib.error
import urllib.request

INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
CONFIG = "application/vnd.oci.image.config.v1+json"
LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def layer(path):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        data = open(path, "rb").read()
        info = tarfile.TarInfo("model.gguf")
        info.size, info.mtime, info.mode, info.uid, info.gid = len(data), 0, 0o644, 0, 0
        tar.addfile(info, io.BytesIO(data))
    tarred = raw.getvalue()
    zipped = io.BytesIO()
    with gzip.GzipFile(fileobj=zipped, mode="wb", mtime=0, filename="") as gz:
        gz.write(tarred)
    return zipped.getvalue(), digest(tarred)


def request(method, url, data=None, headers=None):
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    return urllib.request.urlopen(req, context=ctx, timeout=60)


def push_blob(base, repo, data):
    d = digest(data)
    try:
        request("HEAD", f"{base}/v2/{repo}/blobs/{d}")
        return d
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    loc = request("POST", f"{base}/v2/{repo}/blobs/uploads/").headers["Location"]
    if loc.startswith("/"):
        loc = base + loc
    sep = "&" if "?" in loc else "?"
    request("PUT", f"{loc}{sep}digest={d}", data, {"Content-Type": "application/octet-stream"})
    return d


def push_manifest(base, repo, ref, body, media):
    request("PUT", f"{base}/v2/{repo}/manifests/{ref}", body, {"Content-Type": media})
    return digest(body)


def main():
    registry, ref, path = sys.argv[1:4]
    repo, tag = ref.rsplit(":", 1)
    base = f"https://{registry}"
    blob, diff_id = layer(path)
    layer_digest = push_blob(base, repo, blob)
    manifests = []
    for arch in ("amd64", "arm64"):
        config = json.dumps({"architecture": arch, "os": "linux", "config": {},
                             "rootfs": {"type": "layers", "diff_ids": [diff_id]}},
                            sort_keys=True, separators=(",", ":")).encode()
        config_digest = push_blob(base, repo, config)
        manifest = json.dumps({"schemaVersion": 2, "mediaType": MANIFEST,
                               "config": {"mediaType": CONFIG, "digest": config_digest, "size": len(config)},
                               "layers": [{"mediaType": LAYER, "digest": layer_digest, "size": len(blob)}]},
                              sort_keys=True, separators=(",", ":")).encode()
        d = push_manifest(base, repo, digest(manifest), manifest, MANIFEST)
        manifests.append({"mediaType": MANIFEST, "digest": d, "size": len(manifest),
                          "platform": {"architecture": arch, "os": "linux"}})
    index = json.dumps({"schemaVersion": 2, "mediaType": INDEX, "manifests": manifests},
                       sort_keys=True, separators=(",", ":")).encode()
    print(push_manifest(base, repo, tag, index, INDEX))


if __name__ == "__main__":
    main()
