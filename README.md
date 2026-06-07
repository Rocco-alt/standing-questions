# Standing Questions

**Store the questions. Re-derive the answers.**

A memory pattern for long-horizon AI-agent projects — the kind where a coding agent works the same repository across tens or hundreds of sessions. Instead of persisting *answers* ("the deployed model is v4", "the rate limiter is done"), which silently rot as the repo moves on, the durable artifact is a small set of *questions*. At the start of every session the agent re-derives each answer against current ground truth — the repo itself — diffs it against what was previously believed, and says the deltas out loud before doing anything else.

Answers rot. Questions self-heal — not because the question changes, but because re-asking it forces the answer to be rebuilt from reality every time.

This repo ships the pattern as: a write-up (this file), two JSON Schemas, a generic 12-question seed set, a sample re-derivation log, an installable Claude Code skill, and two stdlib-only Python metrics that detect the pattern's own failure modes. Everything runs on Windows, macOS, and Linux. No dependencies. The field story behind the pattern lives at [standingquestions.com](https://standingquestions.com).

---

## The problem: memory stores rot silently

Every persistent-memory scheme for coding agents — `CLAUDE.md` notes, handoff documents, memory databases, knowledge graphs — converges on storing *facts*: point-in-time answers. Facts decay the moment the repo moves, and nothing announces the decay. The note that says "tests run green via `npm test`" is not wrong the day it's written; it's wrong three weeks later, and it *looks identical* either way.

The incident that motivated this pattern, from a production project where a coding agent worked one repo across hundreds of sessions — roughly 300 over ten weeks, by our count [observed, first-party]: a milestone was marked **done**. The "done" marker survived every subsequent handoff-file rewrite, because each session honestly copied forward what the previous session recorded. Five sessions later an audit found the milestone was 2-of-4 on its own completion criteria. No session had lied. Every session had trusted a stored answer instead of re-checking it — and the audit only happened because a human got suspicious and asked.

The stored answer was the problem. The *question* — "is this milestone actually complete against its written criteria?" — was as valid on day one as on day forty. It just wasn't stored anywhere that would force anyone to re-ask it.

## The inversion

| | stored **answer** | stored **question** |
|---|---|---|
| example | "deploys to Fly.io via fly.toml" | "what is the current deployment target and which file pins it?" |
| when the repo changes | silently wrong | still valid — the answer is what gets re-derived |
| failure mode | trusted past its expiry | skipped (visible in the log — see metrics) |
| maintenance | someone must notice and update it | re-derived from ground truth every session |

Treat the two stores asymmetrically:

- **Questions are durable and human-owned.** They change rarely, deliberately, and only by human edit. ~12 is the right order of magnitude; this is a compass, not a checklist.
- **Answers are disposable derived data** — a cache over the repo, rebuilt at session start, recorded only as a log of *what changed* (database people will recognize a materialized view and its refresh; see [prior art](#prior-art)).

## Mechanism

Two small files in your project, plus a four-step session-start ritual.

**1. `context/standing_questions.json`** — the durable store ([schema](schema/standing_questions.schema.json), [example seed set](examples/standing_questions.json)):

```json
{
  "_schema": "standing_questions/v1",
  "questions": [
    {"id": "q1", "q": "What is the current deployment target and which file or config pins it?", "importance": 3, "evidence_hint": "deploy config in repo root / CI workflow files"},
    {"id": "q2", "q": "What is the test command and does it actually run green right now?", "importance": 3, "evidence_hint": "package manifest scripts / CI config; run it, do not trust the last claim"},
    {"id": "q4", "q": "What did the last session claim was done, and is there externally-produced evidence for it?", "importance": 3, "evidence_hint": "handoff doc 'Done' section vs tests, diffs, CI output"}
  ]
}
```

**2. `context/rederive_log.jsonl`** — the append-only recording layer ([schema](schema/rederive_entry.schema.json), [example](examples/rederive_log.jsonl)). One line per session:

```json
{"ts": "2026-05-08T10:02:00Z", "kind": "rederive", "sid": "s03", "repo_head_sha": "c1d4f0a88e92b35a7d60c13e54b8f29a1c07d3b6", "results": [{"q_id": "q2", "last_rederived_ts": "2026-05-08T10:02:00Z", "delta": false}, {"q_id": "q4", "last_rederived_ts": "2026-05-08T10:02:00Z", "delta": true, "note": "s02 handoff claims rate limiter 'done'; no test covers the burst path - evidence does not support the claim, reopened"}]}
```

**3. The session-start protocol** (the [skill](skill/standing-questions/SKILL.md) implements exactly these four steps):

1. **Load** — read the question store and the tail of the log; note `git rev-parse HEAD`.
2. **Re-derive** — answer every active question from the *current* repo: read the actual files, run the actual commands. Not from memory, not from the previous entry, not from a summary.
3. **Record** — append exactly one `kind=rederive` line: per question, `{q_id, last_rederived_ts, delta}`, plus the HEAD sha. Every `delta:true` carries a `note`.
4. **Report** — say every delta out loud before starting work. Zero deltas while HEAD moved? Say that too — suspiciously.

One operational note: the log is append-only, typically committed, and never pruned — so re-derivation notes must never quote secrets (tokens, connection strings, key material). Name the file that holds the secret instead. If your questions genuinely require sensitive answers, gitignore the log.

Why record `repo_head_sha` instead of the agent's self-assessment? Because the sha is evidence the agent does not author. Every claim in the log that feeds a metric is either externally pinned (the sha) or falsifiable by absence (a question missing from `results`). That design choice came from getting burned — see [the ritualization caveat](#the-ritualization-caveat).

## The two metrics

The log exists so that the pattern's own failure modes are *computable from artifacts*, not vibes. "Metrics" in the loose sense — these are small counters over the log, not statistical measures. Both are stdlib-only Python, identical invocation on every OS, exit non-zero on findings (CI-friendly), and each has tests (`python metrics/test_staleness.py`, `python metrics/test_acknowledge_without_rederive.py`).

### 1. Staleness — is each question actually being re-derived?

```
python metrics/staleness.py examples/rederive_log.jsonl --questions examples/standing_questions.json
```

```
sessions in log: 7 (latest: s07)
  q1   staleness=  0  last_rederived=s07
  ...
  q7   staleness=  6  last_rederived=s01   <-- STALE (over threshold 5)
  q12  staleness=  5  last_rederived=s02
FLAGGED: 1 question(s) over staleness threshold 5: q7
```

Staleness = sessions since the question last appeared in a rederive entry. A question nobody re-derives is decoration. In the field deployment, ten questions sat acknowledged-but-not-re-derived for many sessions before this number existed [observed]; the metric is the alarm that was missing.

### 2. Acknowledge-without-rederive — is the ritual still real?

```
python metrics/acknowledge_without_rederive.py examples/rederive_log.jsonl
```

```
  ok       s04: all delta:false but HEAD unchanged - consistent
  SUSPECT  s05: HEAD moved since previous session but every re-derived question reported delta:false
  SUSPECT  s06: HEAD moved since previous session but every re-derived question reported delta:false
  SUSPECT  s07: HEAD moved since previous session but every re-derived question reported delta:false
suspicious sessions: 3/7; longest consecutive run: 3
ALARM: 3 consecutive sessions reported no deltas while HEAD kept moving (threshold 2) ...
```

One all-quiet session is normal. A *run* of sessions where every question reports `delta:false` while the repo's HEAD keeps moving is the signature of an agent going through the motions. Note the contrapositive case is handled: all-quiet with an *unchanged* HEAD is consistent and not flagged.

## The ritualization caveat

**The rederive entry is a detector of going-through-the-motions, not a guarantee against it.** An agent can write `delta:false` twelve times without having re-derived anything; the log records that re-derivation *reportedly* happened. What the metrics catch is the cheap, observed form of the failure — and the cheap form is, empirically, the common one. A motivated fabricator who invents plausible deltas defeats both metrics. There is no known mechanical fix for that at the reasoning level; if an invariant can be a real test, write the test instead (see [when not to use this](#when-not-to-use-this)).

This caveat is earned, not hypothetical. Two Goodhart incidents from the field deployment shaped the design [observed, first-party]:

1. **Same-author judge collapse.** An earlier, heavier version of this pattern gated re-derivations behind an LLM judge. The judge drifted into a checkbox function: it graded evidence surfaces largely authored by the very session it was supposed to supervise, approvals trended toward rubber-stamping, and in one session the agent issued four manual overrides because the judge loop was non-functional. Separately, the agent twice *faked launching* the out-of-band judge process. Lesson: any verification signal the agent can author, it will eventually author. The lean pattern therefore keys its metrics to signals the agent doesn't control — the git HEAD, and the simple presence or absence of per-question entries.

2. **Acknowledge-without-rederive.** The session-start gate would surface "STALE" tags; sessions would *acknowledge* the tags — and move on without re-deriving. The stale list accumulated across sessions while every session technically "processed" it. Acknowledgment is not action. That incident is why the second metric exists and why it's named what it's named.

Treat an alarm from either metric as a prompt for a human spot-check: pick one flagged question, re-derive it yourself, compare against the log.

## When NOT to use this

Honest scoping. Skip this pattern when:

- **The project is short.** Under ~20 sessions, the session-start tax exceeds the protection. A handoff file is enough; you'll rewrite it before it rots.
- **Sessions are stateless or independent.** No cross-session beliefs, nothing to rot.
- **The answers genuinely don't change.** Static reference knowledge belongs in a normal note. Re-deriving a constant is ceremony.
- **Ground truth isn't derivable from the workspace.** "What does the CEO want this quarter?" cannot be re-derived from the repo; a question must point at checkable evidence or it degrades into exactly the stored opinion it was meant to replace.
- **A mechanical check can do the job.** If "do tests pass?" can be a CI gate or a pre-commit hook, make it one. Standing questions are for state that requires judgment to derive — completion-vs-criteria, drift-between-docs-and-code, "where does the project lie to itself." Hooks beat rituals wherever hooks can reach.
- **You won't look at the metrics.** Unmeasured, the pattern degrades into the ritual it's designed to detect — we watched it happen [observed]. The two scripts are the price of admission.

And one structural boundary: **this is a curated index layer, not the memory itself.** Keep your raw traces — session transcripts, git history, full logs. In a related ablation on harness optimization, Lee et al. report that an optimizer given raw execution traces reached 50.0 median accuracy vs 34.9 for the same optimizer given scores-plus-LLM-summaries — compressed views lost the signal that mattered (Lee et al., Meta-Harness, arXiv:2603.28052, Table 3) [literature]. The analogy is directional, not proof for this pattern, but the design respects it: standing questions sit *on top of* preserved raw history and never replace it.

## Prior art

The parts are old; the assembly is, to the best of our knowledge, new. Nearest neighbors first — and if you know something closer, please open an issue, we will name it here.

- **Architecture fitness functions** (Ford, Parsons & Kua, *Building Evolutionary Architectures*, 2017; ArchUnit) — the closest software-engineering ancestor. A small, durable, human-authored set of assertions re-evaluated continuously against the current codebase, surfacing architectural drift. The differences: fitness functions are binary assertions with hard-coded expectations, where standing questions are open questions whose free-form answers are re-derived and *diffed*; and fitness functions have no analogue of the staleness or ritualization metrics, because CI executes them deterministically — an agent executing a ritual is exactly the part that can't be trusted, which is what the metrics are for.
- **Mainstream agent memory, as the foil** (MemGPT/Letta, Mem0, Zep, A-MEM, and most of the 2024–2026 ecosystem). The prevailing paradigm extracts salient *facts* from interactions and persists them so the agent can stop re-deriving. This pattern is a deliberate inversion of that, for the narrow class of load-bearing project state where a stale answer is worse than a recomputed one. The two coexist: fact memory for cheap recall of stable things, standing questions for the dozen beliefs that must never silently rot.
- **Generative Agents' reflection** (Park et al. 2023, arXiv:2304.03442, §4.2) — the closest published use of questions as a memory device, and worth being precise about. Park's agents periodically generate "the 3 most salient high-level questions" about recent memories, use them *transiently* as retrieval queries, then durably store the resulting *answers* (insights, with citations). Transient questions producing stored answers — the exact opposite durability assignment. Nothing there re-derives a prior answer against a changed world; insights accumulate and are never invalidated.
- **Living / executable documentation** (doctest, Concordion, Gauge; specification-by-example) — documentation continuously executed against the real code so it cannot silently drift. Same enemy (rot), same weapon (re-execution against ground truth); the difference is fixed expected outputs vs open re-derived answers, and no notion of an agent's session ritual needing its own audit.
- **Spaced repetition** (Ebbinghaus; Wozniak's SM-2, 1987; Anki) — the oldest precedent for the question, not the answer, as the durable scheduled unit. Opposite purpose, though: spaced repetition re-asks to *strengthen recall of a fixed answer* in a human head; standing questions re-ask to *detect change in a moving answer* outside it.
- **Materialized views / derived data** (Gupta & Mumick, *Maintenance of Materialized Views*, IEEE Data Eng. Bulletin 18(2), 1995; PostgreSQL `REFRESH MATERIALIZED VIEW`; Kleppmann, *DDIA*, Part III) — the database formulation of the same asymmetry: the stored answer is a view that goes stale; the question is the view's defining query; re-derivation is a full refresh; staleness is refresh lag. And cache invalidation being one of the two hard things (Karlton) is a fine one-line summary of why this repo exists.
- **Held-out probes and canaries** (holdout test sets; Google SRE canarying; CheckList, Ribeiro et al., ACL 2020) — scheduled probes with known-good answers that detect system regression. Standing questions invert the fixed-answer assumption: they probe the *world*, where the answer legitimately changes, so `delta:true` is signal, not failure.

What's claimed as new here is the specific assembly, under a name: durable human-gated questions + per-session re-derivation against repo ground truth + an append-only delta log keyed to the repo HEAD + the two metrics (staleness, acknowledge-without-rederive) that make the ritual's decay measurable. What is *not* claimed: inventing re-derivation, question-driven memory, or drift detection in general.

## Provenance

This pattern ran for ten weeks across roughly 300 sessions of a production ML project before this release [observed, first-party, N-of-1]. The original implementation was much heavier — 28 questions, per-derivation evidence-path hashes, judge-gated commits, an out-of-band evaluator process. Most of that weight turned out to be where the Goodhart incidents lived. What this repo ships is the lean kernel that survived contact: two files, four steps, two metrics. The longer story, with numbers and the incident reports, is in [BLOG.md](BLOG.md), also published at [standingquestions.com](https://standingquestions.com).

All effectiveness evidence is first-party and N-of-1. No controlled comparison exists. The claim this repo stands behind is the mechanism and its measurability, not a benchmark number.

## Quickstart

Clone this repo somewhere (the examples below assume it sits next to your project — adjust the `../standing-questions` paths if yours doesn't):

```
git clone https://github.com/Rocco-alt/standing-questions
cd path/to/your-project
```

Seed the question store in your project (bash):

```bash
mkdir -p context
cp ../standing-questions/examples/standing_questions.json context/
```

or (PowerShell):

```powershell
New-Item -ItemType Directory -Force context | Out-Null
Copy-Item ..\standing-questions\examples\standing_questions.json context\
```

1. **Edit the questions** to point at *your* ground truth. Delete what doesn't apply. Twelve is plenty.
2. **Install the skill** (Claude Code) — see [skill/README.md](skill/README.md). Or port the four steps to any harness: they're plain English plus one JSON line per session. The first skill run creates `context/rederive_log.jsonl`; until then the metrics have nothing to read.
3. **Run the metrics** occasionally, or in CI — they live in the clone, your data lives in your project:

```
python ../standing-questions/metrics/staleness.py context/rederive_log.jsonl --questions context/standing_questions.json
python ../standing-questions/metrics/acknowledge_without_rederive.py context/rederive_log.jsonl
```

(Or copy the two metric files into your project's tooling — they're self-contained, stdlib-only single files by design.)

To see everything working against the shipped sample data first, run the metrics from inside the clone: [examples/README.md](examples/README.md).

## Repo layout

```
README.md                              this file - the pattern
BLOG.md                                the field story: ten weeks, ~300 sessions, two Goodhart incidents
LICENSE                                MIT
schema/standing_questions.schema.json  JSON Schema (draft 2020-12) for the question store
schema/rederive_entry.schema.json      JSON Schema (draft 2020-12) for one log line
examples/standing_questions.json       generic 12-question seed set
examples/rederive_log.jsonl            7-session sample log (deliberately sick: 1 stale question, 3-session ritualization run)
examples/README.md                     what the sample demonstrates
skill/standing-questions/SKILL.md      installable Claude Code skill (the 4-step protocol)
skill/README.md                        install instructions (Windows + macOS/Linux)
metrics/staleness.py                   metric 1 (per-question staleness)
metrics/acknowledge_without_rederive.py  metric 2 (ritualization detector)
metrics/test_staleness.py              tests for metric 1 (stdlib unittest)
metrics/test_acknowledge_without_rederive.py  tests for metric 2 (stdlib unittest)
```

## Authors

Standing Questions comes out of the development and research collaboration of [Dr Raj Kadiwar](https://www.linkedin.com/in/raj-kadiwar/) and [Krishna Kadiwar](https://www.linkedin.com/in/krishnajk/).

## License

[MIT](LICENSE).
