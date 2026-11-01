# Security policy

## Supported versions

| Version | Supported |
|---|---|
| The latest release | yes |
| `main` | yes |
| Older releases | no |

## Reporting a vulnerability

Report privately through GitHub: **Security → Report a vulnerability** on this repository. Email to v@valdemar.ai also works. The process is described at [heyvaldemar.com/security](https://heyvaldemar.com/security/).

You can expect an acknowledgment within 7 days. There is no bounty program; valid, responsibly disclosed reports are credited in the changelog. Please do not open public issues for security reports.

## What this repository is

A reference, not a hosted service. It builds evidence about another repository's admission policies (heyvaldemar/kubernetes-air-gapped-ai-agent) on a throwaway kind cluster, and a vulnerability report here is most likely about the evidence itself: a way to make the gate pass while a control is broken, a signed document that does not say what the cluster showed, or a verification step in the README that accepts something it should refuse. A weakness in the flagship's policies belongs to that repository's security policy.

The planted pods are broken on purpose: unsigned models, models signed by a key the cluster does not trust, images the bundle never carried. The keys that sign the models are made for each run, with no password, and thrown away with the cluster; none is stored here.

## Supply chain

- The flagship's policies are read from its signed release only after cosign and slsa-verifier verify it (`flagship.lock`).
- NIST's catalogs, the command-line tools, C2P and compliance-trestle are pinned by sha256 (`catalogs.lock`, `tools.lock`, `requirements.lock`); C2P's pins are also checked against its publisher's signed checksums.
- Actions are pinned by commit SHA and moved by Dependabot, merged only after the Evidence workflow passes.
- Releases carry a signed source archive with SLSA provenance, and the run's evidence, signed, with its own SLSA provenance.

## Credentials

None. Signatures are keyless, from the workflow's own OIDC identity.
