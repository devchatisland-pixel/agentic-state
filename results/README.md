# Committed results

Most runs stay out of git (their raw data are in `data/`, which is not committed). The folders below are committed
because they are the published record of the cloud experiments. Each holds `dashboard.html` (open it in a browser),
`method.html`, `prompts.html`, `report.md` and the CSV files.

## Cloud screen, 27 Nov 2026 (`bench-screen`, L-B and L-C1)

One run per model. Each folder's `screen.md` says "FAIL" because a screen needs two passing models per run; every
model passed its own criteria. Write-up: [`../docs/archive/proposal_cloud_pilot.md`](../docs/archive/proposal_cloud_pilot.md).

| Folder | Model |
|---|---|
| `20261127-203906-bench-screen-LBLC1` | gpt-oss-20b (Groq) |
| `20261127-203911-bench-screen-LBLC1` | gpt-oss-120b (Groq) |
| `20261127-203916-bench-screen-LBLC1` | qwen3.8-27b (Groq) |
| `20261127-203920-bench-screen-LBLC1` | gemini-flash-lite (Google) |

## Cloud pilot, 28 Nov 2026 (`bench-cloud`, L-B and L-C1)

Write-up: [`../docs/runs/20261128-bench-cloud-pilot.md`](../docs/runs/20261128-bench-cloud-pilot.md).

| Folder | Model |
|---|---|
| `20261128-094450-bench-cloud-LBLC1` | gpt-oss-20b |
| `20261128-094453-bench-cloud-LBLC1` | gpt-oss-120b |
| `20261128-094456-bench-cloud-LBLC1` | qwen3.8-27b |
| `20261128-094458-bench-cloud-LBLC1` | gemini-flash-lite (unfinished: stopped at its daily cap) |

## Bench R, 28 Nov 2026 (`replic-mini`, `replic-quick`; local models)

Three published studies re-run on small local models (`docs/protocol_bench_r.md`). Each folder holds
`dashboard.html`, `report.md` and the `replic_*.csv` files. Write-up:
[`../docs/runs/20261128-bench-r-quick.md`](../docs/runs/20261128-bench-r-quick.md).

| Folder | What |
|---|---|
| `20261128-133646-replic-mini-RMRPRZ` | Smoke test on qwen2.5:3b; found two bugs, fixed before the quick run (not evidence) |
| `20261128-142520-replic-quick-RMRPRZ` | Quick run: qwen2.5:3b, llama3.2:3b, gemma3:4b |
