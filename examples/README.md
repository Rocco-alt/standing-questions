# Examples

Two files you can copy into a real project as a starting point, plus a deliberately imperfect history so the metrics have something to find.

## `standing_questions.json`

A generic ~12-question seed set for a software project, conforming to [`schema/standing_questions.schema.json`](../schema/standing_questions.schema.json). Adapt the wording to your project before using it — a standing question only works if it points at *your* ground truth. Delete the ones that don't apply; fewer well-aimed questions beat a long checklist.

## `rederive_log.jsonl`

A realistic seven-session log, conforming to [`schema/rederive_entry.schema.json`](../schema/rederive_entry.schema.json). It is constructed to demonstrate every behavior the metrics care about:

| Session | What happens | What it demonstrates |
|---|---|---|
| s01 | First derivation of all 12 questions | Baseline entries record `delta:false` with a note |
| s02 | `q2` flips: the test command changed | A genuine delta, caught and noted |
| s02+ | `q7` stops being re-derived (last seen in s01) | Staleness accumulating — reaches 6 by s07, over the default threshold |
| s03 | `q4` flips: the prior session's "done" claim has no supporting evidence | Re-derivation catching a false completion claim — the founding use case |
| s03+ | `q12` stops being re-derived (last seen in s02) | Reaches staleness 5 by s07 — sitting exactly at the default threshold, one quiet session from flagging |
| s04 | All `delta:false`, but HEAD is **unchanged** since s03 | Correctly *not* suspicious — nothing moved, so nothing should have changed |
| s05–s07 | All `delta:false` while HEAD keeps moving; notes disappear | The **acknowledge-without-rederive** (ritualization) signature, three sessions running |

Run the metrics against it from the repo root (same commands in bash and PowerShell):

```
python metrics/staleness.py examples/rederive_log.jsonl --questions examples/standing_questions.json
python metrics/acknowledge_without_rederive.py examples/rederive_log.jsonl
```

Expected: `staleness` flags `q7` (6 sessions stale, threshold 5) and exits 1; the detector flags s05–s07 as a 3-session suspicious run and exits 1. Both exit codes are intentional — this sample history is sick on purpose.

One detail worth noticing: the question that went stale, `q7` ("where does the project lie to itself?"), is exactly the question that would have caught the ritualization in s05–s07. Staleness and ritualization compound — which is why there are two metrics, not one.
