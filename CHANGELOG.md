# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A second engine, the API server, for the three native policies that carry controls (model-volumes, carried-images, models-need-kyverno; `dry_run: true` in the mapping). `scripts/tests.py --dry-run` sends each running pod again, as a new pod under another name, with a server-side dry run, and records what the API server answered, in the shape C2P's vap plugin reads. An admission is a pass for a policy only when the same run saw that policy refuse a planted pod; otherwise it is `error`. The component definition gains a validation component, "Kubernetes API server", with the checks `vap-<policy>` ([ADR 5](docs/decisions/0005-c2p-1-0-beside-its-own-trestle.md)).
- One assessment results for both engines: C2P 1.0.0 aggregates its kyverno-cel plugin's observations of Kyverno's PolicyReports and its vap plugin's observations of the dry run, and every observation names its check, so its engine. SI-7, SR-11 and CM-7(5) now rest on observations from both. The summary shows each control's engines.
- The plant `silent:api-server`: the dry run records no answer, and the gate must find SI-7, SR-11 and CM-7(5) not satisfied, each because the API server reported nothing, while C2P's own posture calls them satisfied with part of their checks reported. Eight plants now. A control is satisfied only when every check the component definition declares for it reported at least one pod, every one a pass.
- An assessment plan per framework, written by `scripts/evidence.py` beside the results that import it, and the component definition in the evidence itself. `scripts/validate.sh` on a directory reads them there, and still reads 1.1.0's and 1.2.0's evidence, whose plans are under `c2p/`.
- Tests for the dry run's outcomes, the engine that reported nothing, C2P's posture, a dry run declared for a policy the API server does not judge, and the silenced engine at the gate, and five that run C2P itself on the recorded run: every declared check observed, Kyverno's reports read as they are, and C2P's posture calling three controls satisfied with the API server silent. 56 tests and 30 changes to the gate's rules, each caught. The fixtures are rebuilt from run 43775335140, which also caught all eight plants.

### Changed

- C2P 1.0.0, the Python implementation, from v2.0.0-rc.1, the Go implementation. It needs compliance-trestle 3.x: with 5.2.1 it does not import, and with 4.0.0 21 of its 31 framework tests fail, so it runs in an environment of its own, `.cache/c2p`, with trestle 3.12.4, every file by hash (`c2p/requirements.lock`, resolved with `--exclude-newer` three days before the move). `jq` and `PyGithub`, declared and imported nowhere, are left out (`c2p/overrides.txt`); jq 1.6.0 does not build on Python 3.13. Its plugins are not in its wheel: the five files the run imports come from the commit its signed v1.0.0 tag names, each by sha256 (`c2p/plugins.lock`). `scripts/install-tools.sh` sets it all up; `tools.lock` no longer pins c2pcli or its Kyverno plugin, and the plugin manifest written for compliance-to-policy-go#322 is gone ([ADR 5](docs/decisions/0005-c2p-1-0-beside-its-own-trestle.md), superseding ADR 2).
- Kyverno's reports reach C2P unchanged. `scripts/collect.py` writes them as the cluster holds them and nothing else: C2P 1.0.0 takes a result's resource from the report's scope and gives a result with no message its own "no message", so the two changes made for v2.0.0-rc.1 are gone, with their three tests and their three changes in `tests/plants.tsv`.
- C2P's verdict on a control is its posture (`c2p/posture.json`), since 1.0.0 writes no findings. A control C2P's posture does not call satisfied is never called satisfied, as C2P's not-satisfied findings were before. Each finding names its engines and C2P's posture, with how many of its expected checks reported.
- The Quickstart asks for Python 3.13 or later, which both locks are resolved for.
- A refused signature or provenance now carries the verifier's own last line (`scripts/flagship.sh` for the flagship's archive). A network fault on the way to Sigstore's TUF mirror ("getting trusted root from TUF") no longer reads like a signature that does not match ("transparency log signature does not match").
- compliance-trestle 5.2.1, from 5.2.0. The release of 2026-11-10 fixes a path traversal in the output path of `trestle import` ([oscal-compass/compliance-trestle#2390](https://github.com/oscal-compass/compliance-trestle/pull/2390)). This repository never calls `trestle import`: it builds its documents with trestle's models and runs `trestle init` and `trestle validate`, so the fix changes nothing it runs. The pin moves so that whoever installs from `requirements.lock` gets the fixed release. The two hashes for trestle are the ones PyPI lists and the release's own assets carry, and both files verify against the release's Sigstore bundles, signed by trestle's `python-push.yml` on main. 5.2.1 pins paramiko 5.1.0 and pydantic 2.14.3 exactly, so both move with it, and pydantic-core 2.50.4 with pydantic; no other dependency moved, and every one was published more than three days before the move.

## [1.2.0] - 2026-11-11

### Added

- Live status, as the account's other reference repositories keep it. With `E2E_RESULTS` set, the gate writes what it decided: a judged run gets one check per control and per admission test and three measured lines (controls satisfied, planted pods refused, control pods admitted), a plant's run one check, whether it was caught, and evidence it cannot read one failed check. Every Evidence job uploads them (`e2e-results-*`), and `.github/workflows/status.yml` rewrites the `status` branch after each run on main with the last 30 days: green days, the streak, the latest run's checks and measurements (`scripts/status.py`, read from GitHub's API). A release's run on its tag is not read. The README's second row of badges reads the branch.
- Two changes to the gate's new output, each caught: a status record that calls a failed check passed, and one that counts every planted pod refused whatever got in. 43 tests and 27 changes to the gate's rules now.
- Static checks with one entry point, `scripts/validate.sh`: the component definition against the mapping, the flagship and NIST's catalogs (`component`); the cluster's nodes against the flagship's (`nodes`); the model server against the flagship's, on the busybox it carries (`workload`); every container image by digest (`images`); trestle on the committed documents (`trestle`); the gate's tests (`gate`); each gate rule switched off in turn (`mutations`). `tests/static/plants.tsv` breaks them 11 ways and `tests/static/plant_violations.py` requires each named check to fail. Given a directory, `validate.sh` is still trestle's validator over a run's evidence, so the README's commands for checking a release work on 1.1.0's archive and on later ones.
- `docs/decisions/`: four records, on resting the mapping on the published control-to-test matrix, on running C2P from its signed release with the plugin manifest written here, on signing the evidence on the tag with the workflow's own identity, and on keeping the SP 800-53 controls in agreement with the flagship's own compliance page.
- The README says how a run goes (a diagram), how to start one (Quickstart), how to take it down (Teardown) and what it costs, from run 41573868103.

### Changed

- CM-14 Signed Components is no longer mapped. It asks for a signature verified against a certificate the organization approves, and the flagship verifies its model against a raw public key. The flagship's own `docs/compliance.md` already said so. Its tests move to SR-11 Component Authenticity: model-unsigned and model-stranger refused, and the game day's signed model refused while Kyverno is away. SR-11's rules are now carried-images, verify-models and models-need-kyverno. Seven controls: 2 SSDF, 4 SP 800-53, 1 AI RMF ([ADR 4](docs/decisions/0004-sp-800-53-agrees-with-the-flagships-page.md)). The evidence fixtures were rebuilt from the same recorded run, and the gate's tests moved off CM-14.
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

[Unreleased]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/heyvaldemar/kubernetes-oscal-evidence/releases/tag/v1.0.0
