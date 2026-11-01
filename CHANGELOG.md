# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-01

### Added

- The admission policies of kubernetes-air-gapped-ai-agent v1.8.0, read from its release archive after its sha256, its cosign signature and its SLSA provenance are verified, brought up on kind with the flagship's two nodes and Kyverno 1.19.2 from the chart it pins.
- `mapping/controls.yaml`: nine NIST controls (SP 800-53 Rev. 5.2.0 CM-14, SI-7, SR-4, SR-11, CM-7(5), SC-24, AC-6; SSDF PW.4.4; AI RMF MANAGE 3.1), each with the policy that carries it, the planted pods that prove it and what it leaves out; `oscal/component-definition.json` built from it with compliance-trestle 5.2.0, checked against NIST's own catalogs.
- The run: the flagship's 18 planted pods (15 it must refuse, 3 it must admit) and its game day step (Kyverno at zero replicas), Kyverno's PolicyReports, C2P v2.0.0-rc.1's Kyverno plugin, assessment results per framework completed and validated with trestle, and a gate that reads them.
- The Evidence workflow on every push, weekly and on each release: the evidence signed keyless with cosign, and on a release attached with SLSA provenance and verified as a stranger would.
- Seven plants that break the run on purpose, each caught in run 41358080026; 21 changes to the gate's own rules, each caught by its tests (`scripts/mutate.py`).

### Found on the way

- C2P v2.0.0-rc.1's release tarballs ship a Kyverno plugin manifest whose sha256 matches neither binary; its Kyverno plugin reads no resource from Kyverno 1.19's per-resource reports, and a result with no message makes c2pcli refuse its own output. Worked around in `scripts/install-tools.sh` and `scripts/collect.py`, as the README describes.
- Kyverno 1.19.2 writes no admission report for a CEL policy whose actions include Deny, reports a native policy only when it is labelled, and evaluates every stored pod as if it were being created. The flagship's verify-models is reported here with its background scan on; egress-node is judged by its admission tests alone.
- Without model-volumes, the flagship admits an image volume from outside the models path: verify-models never sees an image outside its own glob.

[Unreleased]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/releases/tag/v1.0.0
