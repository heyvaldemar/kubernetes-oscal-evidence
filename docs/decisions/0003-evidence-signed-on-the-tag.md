# 3. The evidence is signed on the tag, by the workflow's own identity

- Status: accepted
- Date: 2026-11-01 (1.0.0), recorded 2026-11-02

## Context

The point of OSCAL evidence is that someone who does not trust the author can check it. A file that says controls were satisfied proves nothing about who made it, from which code, or whether it changed afterwards. Whatever signs it has to be checkable by a stranger with public tools, and has to name the code the evidence came from.

## Decision

When a release is published, the Evidence workflow runs on the tag itself, and the evidence it makes is that release's evidence:

1. The run's evidence is packed into a deterministic archive (sorted names, one owner, the commit's time) and signed keyless with cosign. The certificate's identity is this workflow at the tag, `.github/workflows/evidence.yml@refs/tags/<tag>`, from GitHub's OIDC token; the run verifies its own signature before going on.
2. The SLSA generator (slsa-github-generator v2.1.0, referenced by tag as it requires) writes provenance for the archive.
3. A last job attaches the archive, its Sigstore bundle and its provenance to the release, downloads them again as a stranger would, verifies them with cosign and slsa-verifier for that tag, and shows both a copy with one byte appended, which both must refuse.

Every other run is signed the same way with its own ref (pushes and the weekly run as `refs/heads/main`) and kept with the run for 90 days, never attached to a release. A pull request's run is judged, not signed: a pull request from a fork gets no OIDC token, and its evidence is not this repository's.

## Consequences

- No signing key exists to protect, rotate or leak, and the repository holds no secret for it.
- The identity is exact: a signature from any other workflow, branch, tag or repository fails the check the README gives.
- A release's evidence describes the tagged code, not a nearby commit on main.
- The signature depends on Sigstore's public infrastructure and is recorded in its public log; checking it offline needs Sigstore's trust root carried along, as the README shows.

## Alternatives

- **A long-lived signing key in a repository secret.** One more secret to guard, and a leaked key signs anything as this repository, from anywhere, with nothing in the signature to show it.
- **Sign a run on main and attach its evidence to the release.** The certificate would name main, and a stranger could not tie the evidence to the tag from the signature alone.
- **Checksums in the release notes.** A checksum shows that a file is the one listed, not who made it or from what.

## How to explain this to a customer

The evidence for a release was produced by the release itself, from the exact tagged code, and signed by that automated run rather than by anyone's key. Anyone can check this with two free tools, and a copy changed by a single byte fails the check.
