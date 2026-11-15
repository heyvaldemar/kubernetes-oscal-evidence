# 5. C2P 1.0.0 in an environment of its own, with the API server as a second engine

- Status: accepted
- Date: 2026-11-16
- Supersedes: [2. C2P from its release binaries, traced to its publisher's signature](0002-c2p-from-its-signed-release.md)

## Context

C2P v2.0.0-rc.1, the Go implementation, of 2025-11-11, reads one engine and writes one assessment results per engine. Its plugin manifest names a checksum none of its binaries has ([compliance-to-policy-go#322](https://github.com/oscal-compass/compliance-to-policy-go/issues/322)), and its Kyverno plugin needed two changes to Kyverno's reports before it could read them (ADR 2).

C2P 1.0.0, the Python implementation, of 2026-11-10, reads Kyverno's CEL policies through the PolicyReport API and Kubernetes' ValidatingAdmissionPolicy through what a server-side dry run observed, and aggregates several engines into one assessment results. Every observation names its check as well as its rule, so the engine behind it. Measured on 2026-11-15 and 16:

- **Its declared trestle is not the one the evidence is written with.** It declares `compliance-trestle~=3.3`. With compliance-trestle 5.2.1, which this repository pins and which carries the fix for a path traversal in `trestle import` ([compliance-trestle#2390](https://github.com/oscal-compass/compliance-trestle/pull/2390)), it does not import: `RuntimeError: no validator found for <class 'trestle.oscal.common.Finding'>`, its pydantic v1 models over trestle's v2 ones. With 4.0.0, 21 of its 31 framework tests fail. With 3.12.4, the last 3.x release, all 31 pass, and so do the 36 tests of its plugins.
- **Two of its declared dependencies are imported nowhere**: `jq==1.6.0` and `PyGithub==1.58.0`. jq 1.6.0 has no wheel for Python 3.13 and does not build on it ([compliance-to-policy#38](https://github.com/oscal-compass/compliance-to-policy/issues/38), open since 2025-03).
- **Its plugins are not in its wheel.** The package holds `c2p/`; the plugins live beside it in the repository, in `plugins_public/`.
- **It writes no findings and no assessment plan.** Its control-level verdict is its posture (`c2p-posture/v1`), which calls a control satisfied when every check that reported passed, and reports a check that did not report only in the control's coverage: "4 of 5 expected check(s) reported" with the state `satisfied`.
- **ValidatingAdmissionPolicy has no report API.** Kyverno re-evaluates the flagship's four native policies in its background scan and reports them, evaluating every stored pod as if it were being created (README, "What Kyverno's reports needed"). The engine that enforces them is the API server.

## Decision

1. C2P 1.0.0 runs in a virtual environment of its own, `.cache/c2p`, with compliance-trestle 3.12.4, every file by hash (`c2p/requirements.lock`, compiled with `--exclude-newer` three days before the move). The evidence is still written and validated with trestle 5.2.1 (`requirements.lock`); the two meet only in JSON files on disk. `scripts/evidence.py` starts C2P (`scripts/c2p.py`) with that environment's Python.
2. jq and PyGithub are left out by an override that can never match (`c2p/overrides.txt`), since nothing imports them.
3. The five plugin files the run imports come from the commit OSCAL Compass's v1.0.0 tag names, each checked against its sha256 (`c2p/plugins.lock`). The tag is signed, and GitHub verifies the signature.
4. The API server is a second engine for the three native policies that carry controls (`dry_run: true` in the mapping). `scripts/tests.py --dry-run` sends each running pod again, as a new pod under another name, with a server-side dry run, and records what the API server answered, in the shape C2P's vap plugin reads. An admission is a pass for a policy only if the same run saw that policy refuse a planted pod; otherwise the outcome is `error`, never a pass.
5. Kyverno's reports reach C2P unchanged. C2P 1.0.0's kyverno-cel plugin takes a result's resource from the report's scope and gives a result with no message its own "no message"; the two changes `scripts/collect.py` made for v2.0.0-rc.1 are gone.
6. A control is satisfied only when C2P's posture calls it satisfied and every check the component definition declares for it reported at least one pod, every one a pass. An engine that reports nothing is therefore a control not satisfied here, whatever the posture's state; the plant `silent:api-server` shows the gate catching it.
7. `scripts/evidence.py` writes an assessment plan per framework beside its results, since C2P 1.0.0 writes none.

## Consequences

- One assessment results carries both engines, and a control resting on a native policy shows two observations for it: Kyverno's re-evaluation and the API server's own answer. They can disagree, and the evidence would show it.
- Two trestle versions are pinned, and the older one is the one the publisher's tool requires. It writes OSCAL 1.1.3, which trestle 5.2.1 validates; the evidence keeps that version on the results.
- The C2P#322 workaround and the checksum check of v2.0.0-rc.1's signed checksums file are gone with v2.0.0-rc.1. C2P is now traced to its publisher through PyPI's hashes, the release's own assets and the signed tag.
- The dry run judges the workloads this run starts, as `scripts/collect.py` waits for Kyverno to report them. Kyverno's background scan reports every pod in a policy's reach.
- When C2P supports trestle 5, its environment and this repository's become one, and the override goes when C2P stops declaring jq and PyGithub.

## Alternatives

- **Keep v2.0.0-rc.1 for Kyverno and add C2P 1.0.0 for the dry run.** Two tools, two documents per framework: the aggregation that is the point of 1.0.0 would not happen.
- **Install C2P 1.0.0 over trestle 5.2.1 with `--no-deps`.** It does not import.
- **Pin compliance-trestle 3.12.4 for everything.** The evidence would be written with a trestle that predates the path traversal fix.
- **Read the native policies' verdicts from Kyverno only.** That is Kyverno's re-evaluation, not the enforcing engine's answer, and it is wrong for a rule that applies only when a pod is created (egress-node).

## How to explain this to a customer

The compliance tool is the one its publishers released, run in an environment of its own with the library version it was built against, while the evidence documents are written and checked with the current one. Kubernetes' own policies are now asked of Kubernetes itself, by sending each running pod to the API server again without storing it, and the answer sits beside Kyverno's in the same document. If one of them stops answering, the control is not satisfied, and a planted failure in every push shows that it is caught.
