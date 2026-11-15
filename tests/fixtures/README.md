# Fixtures

Files from one real run, [run 43775335140](https://github.com/heyvaldemar/kubernetes-oscal-evidence/actions/runs/43775335140) on 2026-11-15 (`tests/e2e/run.sh` on GitHub's hosted runner, commit f858c3c), with the flagship at v1.8.0 and Kyverno 1.19.2: nothing here is written by hand. Until then they were from a run of 2026-11-01 on kind on an arm64 Mac.

| File | What it is |
|---|---|
| `policyreports.json` | Kyverno's PolicyReports as the cluster held them, as C2P reads them |
| `admission-tests.json` | What the API server answered for each planted pod, the game day step and the workloads |
| `dry-run.json` | The API server's answers to a server-side dry run of each running pod, the second engine (`scripts/tests.py --dry-run`) |
| `evidence/` | The assessment results and `verdict.json` that run produced, every control satisfied |

The tests copy these and break one thing at a time.
