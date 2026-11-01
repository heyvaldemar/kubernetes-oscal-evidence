# Fixtures

Files from one real run of `scripts/run.sh` on 2026-11-01, on kind on an arm64 Mac, with the flagship at v1.8.0: nothing here is written by hand.

| File | What it is |
|---|---|
| `policyreports.json` | Kyverno 1.19.2's PolicyReports as the cluster held them, before `scripts/collect.py` touched them |
| `admission-tests.json` | What the API server answered for each planted pod, the game day step and the workloads |
| `evidence/` | The assessment results and `verdict.json` that run produced, every control satisfied |

The tests copy these and break one thing at a time.
