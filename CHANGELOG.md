# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Live status, as the account's other reference repositories keep it. With `E2E_RESULTS` set, the gate writes what it decided: a judged run gets one check per control and per admission test and three measured lines (controls satisfied, planted pods refused, control pods admitted), a plant's run one check, whether it was caught, and evidence it cannot read one failed check. Every Evidence job uploads them (`e2e-results-*`), and `.github/workflows/status.yml` rewrites the `status` branch after each run on main with the last 30 days: green days, the streak, the latest run's checks and measurements (`scripts/status.py`, read from GitHub's API). A release's run on its tag is not read. The README's second row of badges reads the branch.
- Two changes to the gate's new output, each caught: a status record that calls a failed check passed, and one that counts every planted pod refused whatever got in. 43 tests and 27 changes to the gate's rules now.
- Static checks with one entry point, `scripts/validate.sh`: the component definition against the mapping, the flagship and NIST's catalogs (`component`); the cluster's nodes against the flagship's (`nodes`); the model server against the flagship's, on the busybox it carries (`workload`); every container image by digest (`images`); trestle on the committed documents (`trestle`); the gate's tests (`gate`); each gate rule switched off in turn (`mutations`). `tests/static/plants.tsv` breaks them 11 ways and `tests/static/plant_violations.py` requires each named check to fail. Given a directory, `validate.sh` is still trestle's validator over a run's evidence, so the README's commands for checking a release work on 1.1.0's archive and on later ones.
- `docs/decisions/`: three records, on resting the mapping on the published control-to-test matrix, on running C2P from its signed release with the plugin manifest written here, and on signing the evidence on the tag with the workflow's own identity.
- The README says how a run goes (a diagram), how to start one (Quickstart), how to take it down (Teardown) and what it costs, from run 41573868103.

### Changed

- The whole run moved from `scripts/run.sh` to `tests/e2e/run.sh`, and the good workload from `workload/` to `manifests/model-server.yaml`, where the fleet's focused repositories keep them. The model server names the flagship's busybox by digest instead of a placeholder, and the `workload` check holds it to the flagship's pin. CI creates the kind cluster in a step of its own before the run, which finds it and keeps it; a local run still creates it.
- The control-to-test matrix is pinned at fleet-ops 90e4459, where the LLM03:2025 row says which of the flagship's policies makes each of its twelve refusals, after this repository's `remove:model-volumes` plant showed that verify-models alone admits a model volume from outside the models path. The rows the mapping names are unchanged; v1.1.0's evidence names the earlier pin, 95e3429.

## [1.1.0] - 2026-11-01

### Changed

- The mapping rests on the account's published control-to-test matrix (heyvaldemar/fleet-ops `docs/control-evidence.md`, shown at heyvaldemar.com/evidence), pinned by commit and sha256 in `catalogs.lock`. Every control names its matrix row, and `scripts/component.py` refuses a control with none, a row the pinned matrix does not have, and an SSDF control that is not its own row. Each finding in the assessment results names its rows.
- The control set follows the matrix: SSDF PS.3.2 (the AI-BOM required at admission) is added beside PW.4.4; SP 800-53 CM-14, SI-7, SR-4, SR-11, CM-7(5) and AI RMF MANAGE 3.1 stay, each on a row the matrix already has (LLM03:2025, LLM04:2025, PS.3.2). SC-24 and AC-6 are no longer mapped: no matrix row carries them. Their tests still run and must still pass; the game day step now proves CM-14, whose rules are verify-models and the guard that refuses models while Kyverno is away.
- The gate counts a plant as caught only if every control resting on the planted policy is not satisfied and a pod that policy must refuse got in; a plant caught only for some other reason fails its job.
- 38 tests and 25 changes to the gate's rules, each caught. The evidence fixtures were rebuilt from the same run's recorded reports and admission answers.

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

[Unreleased]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/releases/tag/v1.0.0
