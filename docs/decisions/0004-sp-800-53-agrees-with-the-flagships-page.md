# 4. The SP 800-53 controls agree with the flagship's own compliance page

- Status: accepted
- Date: 2026-11-11 (1.2.0)

## Context

The control-to-test matrix this mapping rests on ([ADR 1](0001-the-mapping-rests-on-the-published-matrix.md)) has SSDF and OWASP rows and no SP 800-53 rows, so which SP 800-53 control a policy lands on was this repository's choice. The flagship publishes its own SP 800-53 mapping, `docs/compliance.md`, and the two disagreed on one control. Up to 1.1.0 this mapping claimed CM-14 Signed Components for verify-models and models-need-kyverno. The flagship's page says CM-14 is not mapped, since 2026-10-20. CM-14 asks that a component be installed only after "verification that the component has been digitally signed using a certificate that is recognized and approved by the organization". The flagship verifies its model against a raw public key written into the policy, with no certificate, and this mapping's own CM-14 entry said exactly that in what it leaves out. Its claim and its caveat could not both hold.

## Decision

CM-14 is not mapped. The tests that proved it go to SR-11 Component Authenticity: model-unsigned and model-stranger refused, and with Kyverno at zero replicas, the signed model refused by the guard. SR-11's rules are now carried-images, verify-models and models-need-kyverno, which is where the flagship's page puts the same evidence. The matrix row stays LLM03:2025. Where an SP 800-53 control appears both here and on the flagship's page, the two say the same thing. CM-7(5) Authorized Software appears only here. It is carried-images' deny-all, permit-by-exception list of digests. The page maps CM-7 to the agent's granted tools instead, which is a different control with different evidence. The two do not disagree.

## Consequences

- Seven controls instead of eight: 2 SSDF, 4 SP 800-53, 1 AI RMF. Every test still runs and the gate still needs each to pass. None of them lost its control: the game day now proves SR-11.
- The `remove:models-need-kyverno` plant now breaks SR-11, and `audit:verify-models` and `phantom-mapping` break SR-11 in place of CM-14.
- Evidence signed for 1.1.0 and before still names CM-14. It was signed as it was, and it stays as it was. 1.2.0's evidence does not name it.
- A control the flagship's page declines is not claimed here unless this repository can show why the page is wrong. When it can, the page is corrected first, as the matrix was in ADR 1.

## Alternatives

- **Keep CM-14 and call the operator's key the organization's approved certificate.** Some assessors would accept a pinned key as the trust anchor. The statement says certificate, and a signed claim should not depend on an assessor reading it generously.
- **Leave the signature plants under SI-7 only.** SI-7 already names model-unsigned and model-stranger. It is about detecting unauthorized change, though, and it says nothing about keeping a counterfeit model out while the verifier is down. That is what the game day shows, and SR-11 is the control that asks for it.

## How to explain this to a customer

The flagship's model is signed with a key the site holds, not with a certificate, so the control for certificate-signed software is not claimed. The same tests are claimed as proof that a counterfeit or unsigned model cannot get in, which is what they show. The flagship's own compliance page says the same.
