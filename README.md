# kubernetes-oscal-evidence

[![Evidence](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/workflows/evidence.yml/badge.svg?branch=main)](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/workflows/evidence.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/heyvaldemar/kubernetes-oscal-evidence/badge)](https://scorecard.dev/viewer/?uri=github.com/heyvaldemar/kubernetes-oscal-evidence)

Out of the box, Kyverno 1.19 wrote no PolicyReport about the flagship's model-signature policy: not for the pod it admitted, not for the pods it refused. An auditor reading the reports would have seen nothing where the cluster's strongest control was working.

This repository brings the admission policies of [kubernetes-air-gapped-ai-agent](https://github.com/heyvaldemar/kubernetes-air-gapped-ai-agent) up on kind on every push, shows them the flagship's own planted pods, and turns what happened into OSCAL assessment results with [OSCAL Compass](https://github.com/oscal-compass), the CNCF sandbox project IBM contributed: C2P reads Kyverno's PolicyReports, compliance-trestle builds and validates the documents. The results are signed with cosign and attached to each release, so a CISO or an auditor can check them without trusting me.

## What one run shows

<!-- numbers: filled from one CI run -->

## The controls

Nine controls from three NIST catalogs, each carried by a policy the flagship ships and proven by planted pods: pods the policy must refuse, and a control pod it must admit. [`mapping/controls.yaml`](mapping/controls.yaml) has every line in full, with what each control leaves out.

| Framework | Control | Carried by | Proven by |
|---|---|---|---|
| SP 800-53 Rev. 5.2.0 | CM-14 Signed Components | verify-models | model-unsigned, model-stranger refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | SI-7 Software, Firmware, and Information Integrity | model-volumes, verify-models | volume-elsewhere, model-unsigned, model-stranger refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | SR-4 Provenance | verify-models | model-nobom refused; model-signed admitted |
| SP 800-53 Rev. 5.2.0 | SR-11 Component Authenticity | carried-images | image-not-carried, volume-not-carried refused; ordinary-pod admitted |
| SP 800-53 Rev. 5.2.0 | CM-7(5) Authorized Software, allow-by-exception | carried-images | image-by-tag, image-not-carried refused; ordinary-pod admitted |
| SP 800-53 Rev. 5.2.0 | SC-24 Fail in Known State | models-need-kyverno | kyverno-away: Kyverno at zero replicas, the signed model refused |
| SP 800-53 Rev. 5.2.0 | AC-6 Least Privilege | egress-node | egress-toleration, egress-tolerate-all, egress-node-name refused; ordinary-pod admitted |
| SP 800-218 SSDF v1.1 | PW.4.4 | verify-models | model-unlicensed, model-licence-mixed, -second, -expression refused; model-licence-concluded admitted |
| AI RMF 1.0 | MANAGE 3.1 | verify-models | model-unsigned, model-nobom, model-unlicensed refused; model-signed admitted |

**Not mapped: SSDF PS.2 and PS.3.** They ask a producer to make release integrity checkable and to archive each release. No admission policy does that. This repository's own releases do (cosign, SLSA provenance), and that is shown by the commands under "Check it yourself", not by a PolicyReport.

The policies and the planted pods are read from the flagship's v1.8.0 release archive after cosign and slsa-verifier verify it ([`flagship.lock`](flagship.lock)). The catalogs are NIST's own OSCAL, pinned by commit and sha256 ([`catalogs.lock`](catalogs.lock)), and every finding names the catalog's own statement id.

## What Kyverno's reports needed

The flagship refuses well and reports nothing, because nothing asked it to. Three settings make Kyverno report on these policies. Each changes what Kyverno writes down, and nothing the API server decides:

1. **A native policy is reported only when it carries the label `reports.kyverno.io/enabled=true`.** Four of the five policies are Kubernetes ValidatingAdmissionPolicies, and the flagship's carry no label. [`scripts/admission.sh`](scripts/admission.sh) adds it to three.
2. **A CEL policy whose actions include Deny gets no admission report, even for a pod it admits.** In Kyverno 1.19.2, the handlers for ImageValidatingPolicy and ValidatingPolicy decide "blocked" from the policy's actions, not from the outcome (`pkg/webhooks/resource/ivpol/handler.go`, `audit()`), and skip the report when it is set. The legacy ClusterPolicy path decides from the outcome. The flagship's verify-models also turns Kyverno's background scan off, so no path reports it at all. Here its background scan is on: Kyverno re-verifies each running pod's model and writes the result. That field, and the operator's public key that the flagship's own install writes in the same way, are the only differences from the flagship's file.
3. **Kyverno's reports controller cannot read a webhook configuration**, which is the parameter of models-need-kyverno. Without a role that lets it, Kyverno logs "forbidden" and gives up on the report of each pod that policy matches; until the role was added, verify-models never reached the model server's report either. One aggregated ClusterRole grants read.

The fifth policy cannot be reported honestly. Kyverno's background scan evaluates every stored object as if it were being created (`pkg/admissionpolicy/validate.go`, `admission.Create`). egress-node refuses a pod that names its node at creation, and every pod the scheduler placed names its node. So the report says "fail" for pods that broke nothing. Every run measures this again: after the reports are collected, egress-node is reported for a moment on the admitted ordinary pod, and the answer is kept as `reporting-probe.json`. AC-6 is judged by its admission tests alone.

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

A control C2P calls not satisfied is never called satisfied here, and a test holds that. [`scripts/gate.py`](scripts/gate.py) reads the signed assessment results themselves, parsed by trestle's models, and exits 1 on any control short of satisfied or any failed admission test, 2 when a document is missing or unreadable. No evidence is a failure, never a pass.

## The plants

<!-- plants: filled from one CI run -->

## What the evidence proves, and what it does not

It proves that in one CI run, on a kind cluster built from the flagship's own node image, the flagship's admission policies at a verified release refused every planted pod they exist to refuse, for the reason they exist to refuse it, admitted the control pods, and that Kyverno's reports of the running pods agreed. It proves that the documents saying so were made by this repository's workflow at a named commit, and have not changed since.

It does not prove:

- **That any system meets a framework.** A control's statement asks for more than a policy does. Each mapping line says what is left out, and an organisation's procedures, people and reviews are never in a PolicyReport.
- **That the flagship's production install is configured this way.** The cluster here is kind, with the network open: the flagship's boundary, its bundle and its registry account are not reproduced. carried-images is given the digests these pods use, where the flagship gives it what its signed bundle carried.
- **Anything about the weights.** The model is a small signed stand-in; admission reads signatures and AI-BOMs, never the file.
- **Anything between runs.** A run is a sample. The schedule runs it weekly, and each run's evidence stands alone.

## Check it yourself

<!-- verification: filled after the release -->

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
