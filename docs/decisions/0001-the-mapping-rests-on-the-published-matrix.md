# 1. The mapping rests on the published control-to-test matrix

- Status: accepted
- Date: 2026-11-01 (1.1.0), recorded 2026-11-02

## Context

The account already publishes a control-to-test matrix: heyvaldemar/fleet-ops `docs/control-evidence.md`, shown at heyvaldemar.com/evidence, which maps SLSA, the SSDF, the OWASP Top 10 for LLM Applications and Article 12 of the EU AI Act onto checks, by hand. Version 1.0.0 of this repository mapped the flagship's policies onto NIST controls on its own: nine of them, SC-24 Fail in Known State and AC-6 Least Privilege among them. Neither of those two has a row in the matrix. The same policies were then mapped one way on the public page and another way in the OSCAL documents, and the two did not agree.

## Decision

Every control in `mapping/controls.yaml` names the matrix row it is the machine-readable form of. SSDF controls are matrix rows themselves; an SP 800-53 or AI RMF control is mapped only where it lands on a row the matrix already has. The matrix is pinned by commit and sha256 in `catalogs.lock`, beside NIST's catalogs, and `scripts/component.py` refuses a control with no row, a row the pinned matrix does not have, and an SSDF control that is not its own row. Each finding in the assessment results names its rows.

## Consequences

- One mapping of controls to checks, in one place. The OSCAL documents are its machine-readable form and cannot say more than the page does.
- Two controls left: SC-24 and AC-6 are not mapped since 1.1.0. Their tests still run and must still pass; the game day step now proves CM-14 instead.
- The evidence corrects the matrix, not the other way round. This repository's `remove:model-volumes` plant showed that verify-models alone admits a model volume from outside the models path; the matrix's LLM03:2025 row was rewritten to say which policy makes each refusal, and the pin here moved from 95e3429 to 90e4459 by a commit of its own.
- The matrix's OWASP rows have no OSCAL catalog to point at. They are named on the controls that map onto them, not mapped on their own.

## Alternatives

- **A mapping of its own, as 1.0.0 had.** Free to follow NIST's catalogs wherever a policy seems to fit, and so free to disagree with the page that the same account publishes.
- **The matrix's rows only, with no SP 800-53 or AI RMF controls.** Faithful to the page, but an auditor working from SP 800-53 would find nothing in the catalog they read, and the OWASP rows would have no OSCAL catalog to name.

## How to explain this to a customer

The controls in these documents are the ones the public evidence page already lists against each test, and a control appears here only where that page shows a test for it. When a run here showed the page was wrong about one policy, the page was corrected first, and this repository moved to the corrected version in a commit anyone can read.
