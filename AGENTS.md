# Working on this repository as an agent

Most of the code here is written by an AI agent, and the decisions and the verification are the maintainer's. This file is what the agent is held to. A reviewer can hold it to the same rules.

## What this repository claims

Only what a named CI run shows. Every number in the README comes from one run's evidence and links to it. A control is called satisfied in one run, by the rule written in `scripts/evidence.py`. Nothing here says that a system meets a framework or holds a certification, because nothing here could show it, and the README says what the evidence does not prove.

## The mapping

A control goes into `mapping/controls.yaml` only where one of the flagship's policies does the work the control's statement asks for, with the planted pods that prove it: at least one the policy must refuse. Each says what it leaves out. `scripts/component.py` refuses a mapping that names a policy, a planted pod or a control that does not exist, and `oscal/component-definition.json` is never edited by hand.

## A check is trusted only after it has failed

A new or changed rule in the gate ships with a test in `tests/test_evidence.py` that feeds it what breaks it, and a line in `tests/plants.tsv` that switches the rule off; `scripts/mutate.py` must report it caught. A change to what the cluster run does ships with a plant in the Evidence workflow's matrix if no plant covers it.

## C2P and Kyverno as they are

The two changes `scripts/collect.py` makes to Kyverno's reports before C2P reads them, and the three settings `scripts/admission.sh` makes so that Kyverno reports at all, are the whole of what this repository changes in the tools' behaviour. Anything more is written in the README beside the reason, or not done. A gap in either tool is reported upstream by the maintainer, in his own words.

## Pins

The flagship by release and archive sha256, verified with cosign and slsa-verifier. Tools by version and sha256 for each platform. compliance-trestle and its dependencies by hash. NIST's catalogs by commit and sha256. Moving any of them is a commit that says what changed and why, after the Evidence workflow passes on it.
