# Fixtures

Files from one real run of `tests/e2e/run.sh` on 2026-11-22, on kind on an arm64 Mac, with the flagship at v1.10.0 and Kyverno 1.20.0, the version it pins: nothing here is written by hand. Before that they were from run 43775335140 on 2026-11-15, on GitHub's hosted runner with the flagship at v1.8.0, and before that from a run of 2026-11-01.

| File | What it is |
|---|---|
| `policyreports.json` | Kyverno's PolicyReports as the cluster held them, as C2P reads them |
| `admission-tests.json` | What the API server answered for each planted pod, the game day step and the workloads |
| `dry-run.json` | The API server's answers to a server-side dry run of each running pod, the second engine (`scripts/tests.py --dry-run`) |
| `evidence/` | The assessment results and `verdict.json` that run produced, every control satisfied |

The tests copy these and break one thing at a time.
