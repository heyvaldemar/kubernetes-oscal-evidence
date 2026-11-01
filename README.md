# kubernetes-oscal-evidence

[![Evidence](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/workflows/evidence.yml/badge.svg?branch=main)](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/workflows/evidence.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/heyvaldemar/kubernetes-oscal-evidence/badge)](https://scorecard.dev/viewer/?uri=github.com/heyvaldemar/kubernetes-oscal-evidence)

Out of the box, Kyverno 1.19 wrote no PolicyReport about the flagship's model-signature policy: not for the pod it admitted, not for the pods it refused. An auditor reading the reports would have seen nothing where the cluster's strongest control was working.

This repository brings the admission policies of [kubernetes-air-gapped-ai-agent](https://github.com/heyvaldemar/kubernetes-air-gapped-ai-agent) up on kind on every push, shows them the flagship's own planted pods, and turns what happened into OSCAL assessment results with [OSCAL Compass](https://github.com/oscal-compass), the CNCF sandbox project IBM contributed: C2P reads Kyverno's PolicyReports, compliance-trestle builds and validates the documents. The results are signed with cosign and attached to each release, so a CISO or an auditor can check them without trusting me.

## What one run shows

From the signed evidence of [run 41358080026](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/runs/41358080026), on commit 85b8287, the flagship at v1.8.0:

| | |
|---|---|
| Controls | 9 of 9 satisfied: 7 from SP 800-53 Rev. 5.2.0, 1 from the SSDF, 1 from the AI RMF |
| Admission tests | 19 recorded: 16 planted pods refused, each by the policy the mapping names and with the flagship's own expected words, and 3 control pods admitted |
| The game day | Kyverno's admission controller scaled to zero: its webhook configuration went with it, and the API server's own guard refused the signed model |
| Kyverno's reports | 6 PolicyReports, 9 results, every one a pass: the model server passed all four reported policies; the ordinary pod and Kyverno's four pods passed carried-images |
| C2P | 3 assessment plans and 3 assessment results; 4 observations with 9 subjects for SP 800-53, and no finding of its own |
| trestle | 7 documents valid: the component definition, the plans, the results |
| Signature | keyless, from this workflow's identity, verified in the same run |
| The probe | egress-node reported for a moment on the admitted ordinary pod: Kyverno's background scan said "fail" |

Every push runs it again. So does a weekly schedule, and so does every release, whose evidence is made by a run on the tag itself.

## The controls

This is the machine-readable form of rows that already exist. The account's [control-to-test matrix](https://github.com/heyvaldemar/fleet-ops/blob/95e34294b69dd54ffa90fe2bcce542b6745ed267/docs/control-evidence.md), shown at [heyvaldemar.com/evidence](https://heyvaldemar.com/evidence/#frameworks-h), maps SLSA, the SSDF, the OWASP Top 10 for LLM Applications and Article 12 of the EU AI Act onto checks, by hand. Every control here names the matrix row it rests on, and [`scripts/component.py`](scripts/component.py) refuses a row the pinned matrix does not have. The SSDF controls are matrix rows themselves. An SP 800-53 or AI RMF control is here only where it maps onto a row the matrix already has; the OWASP rows have no OSCAL catalog to point at, so they are named on the controls that map onto them.

Eight controls, each carried by a policy the flagship ships and proven by planted pods: pods the policy must refuse, and a control pod it must admit. They are the flagship's e2e check 9, which the matrix's LLM03 row counts as 12 planted pods refused and 2 controls admitted, and its game day step. [`mapping/controls.yaml`](mapping/controls.yaml) has every line in full, with what each control leaves out.

| Framework | Control | Matrix row | Carried by | Proven by |
|---|---|---|---|---|
| SSDF v1.1 | PS.3.2 | PS.3.2, LLM04:2025 | verify-models | model-nobom refused; model-signed admitted |
| SSDF v1.1 | PW.4.4 | PW.4.4, LLM03:2025 | verify-models | model-unlicensed, model-licence-mixed, -second, -expression refused; model-licence-concluded admitted |
| SP 800-53 Rev. 5.2.0 | CM-14 Signed Components | LLM03:2025 | verify-models, models-need-kyverno | model-unsigned, model-stranger refused; with Kyverno at zero replicas, the signed model refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | SI-7 Software, Firmware, and Information Integrity | LLM03:2025, LLM04:2025 | model-volumes, verify-models | volume-elsewhere, model-unsigned, model-stranger refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | SR-4 Provenance | PS.3.2, LLM04:2025 | verify-models | model-nobom refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | SR-11 Component Authenticity | LLM03:2025 | carried-images | image-not-carried, volume-not-carried refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | CM-7(5) Authorized Software, allow-by-exception | LLM03:2025 | carried-images | image-by-tag, image-not-carried refused; model-signed admitted |
| AI RMF 1.0 | MANAGE 3.1 | LLM03:2025 | verify-models | model-unsigned, model-nobom, model-unlicensed refused; model-signed admitted |

**Not mapped.** SSDF PS.2.1 and PS.3.1 ask a producer to make release integrity checkable and to archive each release; no admission policy does that, and the matrix shows them through release signing. Version 1.0.0 also mapped SC-24 Fail in Known State and AC-6 Least Privilege; no matrix row carries either, so 1.1.0 does not. Their tests still run and the gate still needs them to pass: the game day now proves CM-14, and the egress-node pods prove no control. The matrix's gaps stay gaps; nothing here closes one.

The policies and the planted pods are read from the flagship's v1.8.0 release archive after cosign and slsa-verifier verify it ([`flagship.lock`](flagship.lock)). The catalogs are NIST's own OSCAL, and they and the matrix are pinned by commit and sha256 ([`catalogs.lock`](catalogs.lock)). Every finding names the catalog's own statement id and the matrix rows it rests on.

## What Kyverno's reports needed

The flagship refuses well and reports nothing, because nothing asked it to. Three settings make Kyverno report on these policies. Each changes what Kyverno writes down, and nothing the API server decides:

1. **A native policy is reported only when it carries the label `reports.kyverno.io/enabled=true`.** Four of the five policies are Kubernetes ValidatingAdmissionPolicies, and the flagship's carry no label. [`scripts/admission.sh`](scripts/admission.sh) adds it to three.
2. **A CEL policy whose actions include Deny gets no admission report, even for a pod it admits.** In Kyverno 1.19.2, the handlers for ImageValidatingPolicy and ValidatingPolicy decide "blocked" from the policy's actions, not from the outcome (`pkg/webhooks/resource/ivpol/handler.go`, `audit()`), and skip the report when it is set. The legacy ClusterPolicy path decides from the outcome. The flagship's verify-models also turns Kyverno's background scan off, so no path reports it at all. Here its background scan is on: Kyverno re-verifies each running pod's model and writes the result. That field, and the operator's public key that the flagship's own install writes in the same way, are the only differences from the flagship's file.
3. **Kyverno's reports controller cannot read a webhook configuration**, which is the parameter of models-need-kyverno. Without a role that lets it, Kyverno logs "forbidden" and gives up on the report of each pod that policy matches; until the role was added, verify-models never reached the model server's report either. One aggregated ClusterRole grants read.

The fifth policy cannot be reported honestly. Kyverno's background scan evaluates every stored object as if it were being created (`pkg/admissionpolicy/validate.go`, `admission.Create`). egress-node refuses a pod that names its node at creation, and every pod the scheduler placed names its node. So the report says "fail" for pods that broke nothing. Every run measures this again: after the reports are collected, egress-node is reported for a moment on the admitted ordinary pod, and the answer is kept as `reporting-probe.json`. So egress-node is judged by its admission tests alone, and since 1.1.0 no control rests on it.

## What C2P needed

C2P v2.0.0-rc.1, the Go implementation, run from its release binaries after their checksums file verifies against its publisher's cosign signature. Three things stood between its Kyverno plugin and Kyverno 1.19's reports:

1. **The plugin's manifest names the wrong checksum.** The release tarballs ship `c2p-kyverno-manifest.json` with a sha256 that matches neither the linux-amd64 nor the darwin-arm64 binary beside it, and c2pcli refuses to start the plugin: "checksums did not match". [`scripts/install-tools.sh`](scripts/install-tools.sh) writes the manifest from the binary it has just verified.
2. **Every observation came out with no subjects.** Kyverno 1.19 writes one report per resource and names the resource once, in the report's `scope`; the plugin reads it from each result's `resources`, which Kyverno leaves empty. C2P then calls every control not satisfied, whatever the results say.
3. **A passing result breaks C2P's own validation.** Kyverno gives a pass no message, the plugin copies the message into each subject's `reason`, and C2P's schema check refuses the empty value. c2pcli exits 1 and writes nothing.

[`scripts/collect.py`](scripts/collect.py) makes exactly two changes to the reports before C2P reads them: the scope copied into each result, and a message where Kyverno gave none ("pass; Kyverno gave no message"). The evidence keeps the reports as the cluster held them, and a test fails if a third change appears.

C2P writes findings only for controls it judges not satisfied, and names each target `<control>_smt`, the SP 800-53 convention. NIST's SSDF and AI RMF catalogs name their statements `statement_PW.4.4` and `SA-MANAGE_3.1`. So the findings in the evidence are written by [`scripts/evidence.py`](scripts/evidence.py), one per control, with the catalog's own statement id. C2P's own plan and results stay in the evidence, under `c2p/`.

## How a control is judged

A control is satisfied in a run only when all three hold:

1. C2P made no finding for it.
2. Every policy that carries it, and that Kyverno reports on, has at least one running pod in the reports, and every result for it is a pass.
3. Every test that proves it did what the mapping says: refused by the named policy, with the flagship's own expected words, or admitted.

A control C2P calls not satisfied is never called satisfied here, and a test holds that. [`scripts/gate.py`](scripts/gate.py) reads the signed assessment results themselves, parsed by trestle's models, and exits 1 on any control short of satisfied or any failed admission test, 2 when a document is missing or unreadable. No evidence is a failure, never a pass. Given a plant, the gate passes only if every control resting on the planted policy is not satisfied and a pod that policy must refuse got in: caught for the planted reason, not for some other.

## The plants

A gate that has never failed proves nothing. Every push runs the whole thing seven more times, broken on purpose, and each of those jobs passes only if the gate fails, and fails on every control that rests on what was broken:

| Plant | What it breaks | Not satisfied | Tests failed |
|---|---|---|---|
| `remove:verify-models` | The signature policy is never applied | CM-14, SI-7, SR-4, SC-24, PW.4.4, MANAGE 3.1 | 11 of 19 |
| `audit:verify-models` | The signature policy records instead of refusing, and a model nobody signed runs | CM-14, SI-7, SR-4, PW.4.4, MANAGE 3.1 | 7 |
| `phantom-mapping` | The mapping names `verify-model-signatures`, a policy the flagship does not have | CM-14, SI-7, SR-4, PW.4.4, MANAGE 3.1 | 7 |
| `remove:carried-images` | No list of carried digests | SR-11, CM-7(5) | 3 |
| `remove:model-volumes` | No native check on where model weights come from | SI-7 | 1 |
| `remove:models-need-kyverno` | No guard while Kyverno is away | SC-24 | 1 |
| `remove:egress-node` | Nothing keeps pods off the egress node | AC-6 | 3 |

Each was caught in [run 41358080026](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/runs/41358080026). Three of them say more than that the gate works:

- **`audit:verify-models` is the PolicyReport path.** With the policy recording rather than refusing, the unsigned model ran, Kyverno's report said "fail" for its pod, and C2P turned that into its own not-satisfied finding. The other plants reach the gate through missing reports and failed tests; this one through a report that names a violation.
- **`phantom-mapping` is refused twice.** The mapping check stops it before anything runs. Built anyway, the run refuses it on its own: Kyverno reports `verify-models`, nothing reports `verify-model-signatures`, and every test is refused by a policy the mapping does not name.
- **`remove:model-volumes` admitted the model from elsewhere.** The flagship's verify-models carries the same rule, "model weights come only from registry.boundary.internal:5000/models", and both policies print it. But Kyverno evaluates verify-models only for images that match its own `matchImageReferences` glob, so an image volume from anywhere else never reaches it. model-volumes is the only rule that holds the path, not a second layer.

The gate's own rules are shown their failures too. [`tests/test_evidence.py`](tests/test_evidence.py) runs them on one real run's files, breaking one thing at a time, and [`scripts/mutate.py`](scripts/mutate.py) switches each rule off in a copy of the scripts, from [`tests/plants.tsv`](tests/plants.tsv), and requires a named test to fail. The first time it ran, 4 of 20 changes went unnoticed: one test passed because the changed gate crashed rather than because it judged, one change sat on a branch its test never reached, one rule is backed by the next so that switching it off alone changes nothing, and one test broke the mapping in more ways than the rule it was written for. The tests and the changes were fixed until each of the 21 now listed is caught by its own test.

## What the evidence proves, and what it does not

It proves that in one CI run, on a kind cluster built from the flagship's own node image, the flagship's admission policies at a verified release refused every planted pod they exist to refuse, for the reason they exist to refuse it, admitted the control pods, and that Kyverno's reports of the running pods agreed. It proves that the documents saying so were made by this repository's workflow at a named commit, and have not changed since.

It does not prove:

- **That any system meets a framework.** A control's statement asks for more than a policy does. Each mapping line says what is left out, and an organisation's procedures, people and reviews are never in a PolicyReport.
- **That the flagship's production install is configured this way.** The cluster here is kind, with the network open: the flagship's boundary, its bundle and its registry account are not reproduced. carried-images is given the digests these pods use, where the flagship gives it what its signed bundle carried.
- **Anything about the weights.** The model is a small signed stand-in; admission reads signatures and AI-BOMs, never the file.
- **Anything between runs.** A run is a sample. The schedule runs it weekly, and each run's evidence stands alone.

## Check it yourself

Each release carries the run's evidence beside its source: `kubernetes-oscal-evidence-<tag>-evidence.tar.gz`, its Sigstore bundle, and its SLSA provenance. The evidence was made by a run of the Evidence workflow on the tag itself, and nothing in this repository needs to be trusted to check it.

```sh
TAG=v1.0.0
NAME=kubernetes-oscal-evidence-$TAG-evidence
gh release download "$TAG" -R heyvaldemar/kubernetes-oscal-evidence -p "$NAME.*"
```

**The signature, offline.** cosign needs Sigstore's trust root and the bundle, nothing else. On any connected machine `cosign initialize` writes the trust root to `~/.sigstore/root/tuf-repo-cdn.sigstore.dev/targets/trusted_root.json`; carry that file across with the evidence.

```sh
cosign verify-blob "$NAME.tar.gz" --bundle "$NAME.tar.gz.sigstore.json" --trusted-root trusted_root.json \
  --certificate-identity "https://github.com/heyvaldemar/kubernetes-oscal-evidence/.github/workflows/evidence.yml@refs/tags/$TAG" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

The identity is exact: the workflow file and the tag. A signature from any other workflow, branch or repository fails.

**The provenance.** slsa-verifier checks that the archive was built by GitHub's runner from this repository at the tag; it reads Sigstore's public log, so it needs the network.

```sh
slsa-verifier verify-artifact "$NAME.tar.gz" --provenance-path "$NAME.intoto.jsonl" \
  --source-uri github.com/heyvaldemar/kubernetes-oscal-evidence --source-tag "$TAG"
```

**The documents.** Unpack it and read `evidence/summary.md` first. The OSCAL documents are `evidence/assessment-results-*.json`, with C2P's own plans and results under `evidence/c2p/` and Kyverno's reports as the cluster held them under `evidence/policyreports/`. Validate them with compliance-trestle, and run the gate on them from the release's source archive (`kubernetes-oscal-evidence-<tag>.tar.gz`, signed and verifiable the same way, with `release-assets.yml` in place of `evidence.yml`):

```sh
tar -xzf "$NAME.tar.gz"
python3 -m venv .venv && .venv/bin/pip install --require-hashes --no-deps -r requirements.lock
PATH="$PWD/.venv/bin:$PATH" bash scripts/validate.sh evidence
PATH="$PWD/.venv/bin:$PATH" python3 scripts/gate.py evidence
```

The release workflow ran the same two checks on the files the release now holds, and showed each a copy of the archive with one byte appended, which both refused.

## Run it yourself

```sh
python3 -m venv .venv && .venv/bin/pip install --require-hashes --no-deps -r requirements.lock
PATH="$PWD/.venv/bin:$PATH" bash scripts/run.sh
```

It needs Docker, curl, jq, openssl and Python 3.11 or later; everything else is downloaded and checked by hash. `PLANT=remove:verify-models` (or any plant below) breaks it on purpose, and the gate must catch it. `REGISTRY_PORT=5055` if port 5000 is taken, as macOS takes it for AirPlay.

## Repository

| Path | What it is |
|---|---|
| `mapping/controls.yaml` | The mapping, written for a person: each control, the policy that carries it, the tests that prove it, what it leaves out |
| `oscal/component-definition.json` | The same mapping as an OSCAL component definition, made by `scripts/component.py` with trestle's models |
| `flagship.lock`, `catalogs.lock`, `tools.lock`, `requirements.lock` | What is fetched, and the hash it must have |
| `kind/cluster.yaml` | The flagship's two nodes; CI checks they are the same |
| `workload/model-server.yaml` | The good workload: a model server shaped like the flagship's |
| `scripts/` | The run, step by step; `run.sh` is all of it |
| `tests/` | The gate's tests on one real run's files, and `plants.tsv`, each rule of the gate switched off in turn |

## Questions, bugs and changes

Open an [issue](https://github.com/heyvaldemar/kubernetes-oscal-evidence/issues) for a bug, a question or an idea. Security reports go privately, as [SECURITY.md](SECURITY.md) describes.

## How this is built

One maintainer and an AI agent. The agent writes most of the code; the decisions are mine, and so is the verification. Nothing merges on the agent's report that it works: it merges on the checks above, and each of them has been shown the failure it exists to catch. The rules the agent works under are in [AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE).
