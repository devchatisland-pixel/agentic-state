# Screen 20261127-203906-bench-screen-LBLC1

Decision: **FAIL** (a module passes when at least 2 models pass every criterion; criteria fixed before the screen ran).

## LB: FAIL (1 models pass: gpt-oss-20b)

| Model | Criterion | Value | Pass | Rule |
|---|---|---|---|---|
| gpt-oss-20b | finished | 36/36 trials | yes | every planned trial finished (none left by the time cap, none failed) |
| gpt-oss-20b | solo filter | 6/6 (100%) | yes | at least 4 instances passed alone |
| gpt-oss-20b | usable replies | 36/36 (100%) | yes | at least 95% of the decisions usable |
| gpt-oss-20b | room to rise | 0/12 (0%) | yes | a direct order is obeyed in at most 75% of the decisions (room for the chain to raise it) |
| gpt-oss-20b | no position habit | 4/36 (11%) | yes | the first-listed of the 4 options is chosen in at most 50% of the decisions (their order is counterbalanced: about 25% means no habit) |

## LC1: FAIL (1 models pass: gpt-oss-20b)

| Model | Criterion | Value | Pass | Rule |
|---|---|---|---|---|
| gpt-oss-20b | finished | 60/60 trials | yes | every planned trial finished (none left by the time cap, none failed) |
| gpt-oss-20b | solo filter | 6/6 (100%) | yes | at least 4 instances passed alone |
| gpt-oss-20b | usable replies | 60/60 (100%) | yes | at least 95% of the decisions usable |
| gpt-oss-20b | uses the facts | 12/12 (100%) | yes | control cell (plain statements, no members agreeing, no charter): the adviser who is wrong leaves in at least 80% of the ballots |
| gpt-oss-20b | knows who is right | 48/48 (100%) | yes | in council, the ballot names the adviser whose figure matches the log in at least 80% of the ballots |
| gpt-oss-20b | not stuck | 35/48 (73%) | yes | the dissenter is dropped in 10% to 90% of all ballots (not always the same adviser whatever happens) |
| gpt-oss-20b | no position habit | 23/48 (48%) | yes | the first-listed adviser is dropped in 25% to 75% of all ballots (the order of the names is counterbalanced: about 50% means no habit) |
