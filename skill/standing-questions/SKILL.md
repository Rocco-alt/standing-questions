---
name: standing-questions
description: Session-start re-derivation of the project's standing questions against the current repo. Use at the start of a session, before any other work, whenever the project has a context/standing_questions.json store. Re-derives every active question from ground truth, appends one kind=rederive entry to context/rederive_log.jsonl, and reports every delta out loud.
---

# Standing Questions — session-start re-derivation

Answers rot; questions self-heal. The questions in `context/standing_questions.json` are durable; the answers are a cache you are about to refresh. Do all four steps, in order, before the day's work.

## Step 1 — Load

Read `context/standing_questions.json` and the last 2 entries of `context/rederive_log.jsonl` (if the log exists). Run `git rev-parse HEAD` and note the sha. Pick this session's `sid`: increment the previous entry's (prior `s17` → this is `s18`); if there is no log yet, use `s01`.

## Step 2 — Re-derive

For every question with status `active`, derive a fresh answer against the CURRENT repo: read the actual files, run the actual commands the question points at. The `evidence_hint` is where to start, not where to stop. Do NOT answer from memory, from the previous log entry, or from any summary — the entire value of this ritual is that the answer comes from ground truth, not from what you already believe. Then compare: did the answer materially change vs. what the project last recorded or believed? If a question's evidence can no longer be found, that IS a material change.

## Step 3 — Record

Append exactly ONE line to `context/rederive_log.jsonl` (create the file if missing; never edit or delete existing lines). It must match `schema/rederive_entry.schema.json`:

```json
{"ts": "<ISO-8601 now>", "kind": "rederive", "sid": "<sid from step 1>", "repo_head_sha": "<sha from step 1>", "results": [{"q_id": "q1", "last_rederived_ts": "<ISO-8601 now>", "delta": false}, {"q_id": "q2", "last_rederived_ts": "<ISO-8601 now>", "delta": true, "note": "what changed"}]}
```

One result per question actually re-derived. Every `delta:true` MUST carry a `note` saying what changed — a delta with no note is unauditable.

## Step 4 — Report out loud

Before starting any other work, tell the user every `delta:true` as one line each ("DELTA q4: last session's 'done' claim has no supporting test"). If there are ZERO deltas and HEAD differs from the previous entry's `repo_head_sha`, say exactly that and treat it with suspicion — "no deltas despite N commits since last session" is the known ritualization signature, so name the two or three questions most likely affected by those commits and double-check them.

## Hard rules

- The question store is human-owned: never add, edit, or retire questions. Propose changes to the user instead.
- The log is append-only: never rewrite history.
- The log is typically committed and never pruned: never quote secrets (tokens, connection strings, key material) in a note — name the file that holds them instead.
- Re-derivation means reading current ground truth. Acknowledging that a question exists is not re-deriving it.
