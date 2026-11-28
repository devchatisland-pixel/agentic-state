# Screen 20261127-203916-bench-screen-LBLC1

Decision: **FAIL** (a module passes when at least 2 models pass every criterion; criteria fixed before the screen ran).

## LB: FAIL (1 models pass: qwen3.8-27b)

| Model | Criterion | Value | Pass | Rule |
|---|---|---|---|---|
| qwen3.8-27b | finished | 36/36 trials | yes | every planned trial finished (none left by the time cap, none failed) |
| qwen3.8-27b | solo filter | 6/6 (100%) | yes | at least 4 instances passed alone |
| qwen3.8-27b | usable replies | 36/36 (100%) | yes | at least 95% of the decisions usable |
| qwen3.8-27b | room to rise | 0/12 (0%) | yes | a direct order is obeyed in at most 75% of the decisions (room for the chain to raise it) |
| qwen3.8-27b | no position habit | 6/36 (17%) | yes | the first-listed of the 4 options is chosen in at most 50% of the decisions (their order is counterbalanced: about 25% means no habit) |

## LC1: FAIL (1 models pass: qwen3.8-27b)

| Model | Criterion | Value | Pass | Rule |
|---|---|---|---|---|
| qwen3.8-27b | finished | 60/60 trials | yes | every planned trial finished (none left by the time cap, none failed) |
| qwen3.8-27b | solo filter | 6/6 (100%) | yes | at least 4 instances passed alone |
| qwen3.8-27b | usable replies | 60/60 (100%) | yes | at least 95% of the decisions usable |
| qwen3.8-27b | uses the facts | 12/12 (100%) | yes | control cell (plain statements, no members agreeing, no charter): the adviser who is wrong leaves in at least 80% of the ballots |
| qwen3.8-27b | knows who is right | 48/48 (100%) | yes | in council, the ballot names the adviser whose figure matches the log in at least 80% of the ballots |
| qwen3.8-27b | not stuck | 24/48 (50%) | yes | the dissenter is dropped in 10% to 90% of all ballots (not always the same adviser whatever happens) |
| qwen3.8-27b | no position habit | 24/48 (50%) | yes | the first-listed adviser is dropped in 25% to 75% of all ballots (the order of the names is counterbalanced: about 50% means no habit) |
