# 2. C2P from its release binaries, traced to its publisher's signature

- Status: accepted
- Date: 2026-11-01 (1.0.0), recorded 2026-11-02

## Context

C2P, OSCAL Compass's compliance-to-policy tool, turns the component definition and Kyverno's PolicyReports into OSCAL assessment plans and results. This repository uses the Go implementation, v2.0.0-rc.1, published as release tarballs for each platform with a checksums file that the project signs with cosign from its release workflow. Its Kyverno plugin runs only if the plugin's manifest names the binary's sha256, and the manifest in the v2.0.0-rc.1 tarballs names 833ce6b7..., which is neither the linux-amd64 nor the darwin-arm64 binary beside it. c2pcli then stops with "checksums did not match".

## Decision

C2P runs from its release binaries, and each one is traced to its publisher on every install (`scripts/install-tools.sh`):

1. `tools.lock` pins c2pcli and the Kyverno plugin by version and by sha256 for each platform, and a download with another hash is not installed.
2. The release's checksums file must verify with cosign against its signature and certificate, for the identity of OSCAL Compass's release workflow. That release was signed by a run on main, not on the tag; the certificate says so, and the identity pinned is that one.
3. Every C2P hash in `tools.lock` must be a line of that signed file.

The plugin's manifest is then written here, from the binary just checked. It is the one file of C2P's this repository writes, and the gap is reported upstream as [compliance-to-policy-go#322](https://github.com/oscal-compass/compliance-to-policy-go/issues/322).

## Consequences

- What runs is what OSCAL Compass's release workflow published, checked on every install, on a laptop as in CI.
- The manifest's checksum is ours, not the publisher's. It is written from a binary whose hash is pinned and listed in the signed file, so it vouches for nothing the signature does not.
- When a release ships a manifest that matches its binary, the rewrite goes. Moving the pin needs the new release's checksums file to verify the same way.
- C2P's reading of Kyverno 1.19's reports needed two changes to the reports themselves (`scripts/collect.py`), which the README describes. They are a separate matter: they change what C2P is given, not what it is.

## Alternatives

- **Build C2P from source at the release commit.** It would carry a manifest that matches, but the binary would be one nobody else has, with no signature from its publisher to check it against, and one more toolchain to pin.
- **Patch c2pcli to skip the plugin's checksum.** It would change the tool's behaviour to get past its own safety check, which is exactly what this repository does not do to its tools.
- **Wait for a release with a matching manifest.** v2.0.0-rc.1, of 2025-11-11, is still the latest release, and the evidence would have waited with it.

## How to explain this to a customer

The compliance tool used here is the one its publishers released, checked against their signature every time it is installed. One of its files carried a wrong checksum; it is rewritten here from the verified program, the publishers have been told in a public issue, and the README says so.
