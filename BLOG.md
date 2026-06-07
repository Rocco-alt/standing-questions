# Answers rot. Store questions instead.

*By [Dr Raj Kadiwar](https://www.linkedin.com/in/raj-kadiwar/) and [Krishna Kadiwar](https://www.linkedin.com/in/krishnajk/).*

*Standing Questions: a memory pattern for long-horizon AI-agent projects, distilled from ten weeks and a few hundred sessions of getting agent memory wrong. Code, schemas, and metrics: [github.com/Rocco-alt/standing-questions](https://github.com/Rocco-alt/standing-questions). Canonical home of this post: [standingquestions.com](https://standingquestions.com).*

A note on epistemics before anything else: everything below comes from the two of us running one production project. Where we state a fact we tag it **[observed]** (we saw it in our own logs and artifacts), **[inferred]** (our interpretation of what we saw), or **[literature]** (someone else's published result). There is no control group. Nothing here is a benchmark. It's a field report with the receipts we can show.

## The incident

For ten weeks we ran a production ML project almost entirely through a coding agent — Claude Code, working the same repository session after session; roughly 300 working sessions by the end, counting the continuation lanes long sessions split into [observed].

A few weeks in, a milestone got marked **done**. The marker was written into the handoff notes, and every subsequent session faithfully carried it forward, because that's what good session hygiene looks like: read the notes, trust the notes, build on the notes.

Five sessions later, an audit found the milestone was 2-of-4 on its own written completion criteria [observed].

No session had lied. The work had genuinely narrowed across sessions — recommendation became plan, plan became "shipped the core part" — and each session honestly believed it was finishing what the previous session meant. The stored answer ("done") outlived the reality it described. And the thing that finally caught it wasn't the memory system, the notes, or the agent. It was one of us, getting suspicious and asking [observed].

That stung, because the question that would have caught it — *"is this milestone actually complete against its written criteria?"* — was perfectly stateable on day one. It just didn't live anywhere that forced anyone to re-ask it.

## Why answer-stores rot

By that point we had tried the standard things.

A memory file and handoff notes: they work, until a stored fact quietly goes stale and every later session inherits it as truth. The notes that say "tests green via `npm test`" look identical the day they're right and the month they're wrong.

Automatic logging of everything: we once had hooks auto-logging every tool call. That produced a 20.5 MB log that was roughly 99% mechanical chatter — file opened, command ran — and captured none of the reasoning that actually mattered [observed]. Expensive capture of the low-value signal.

The shape of the problem, as we'd state it now [inferred]: agent memory schemes persist *answers*, and answers are point-in-time. The repo moves; the answer doesn't; nothing announces the divergence. The failure isn't dramatic — it's a slow accumulation of small stale beliefs that sessions act on without re-checking, until one of them is load-bearing.

## The inversion

So we inverted what gets stored.

The durable artifact became a small set of **questions** — a dozen or so, version-controlled, edited only by us. Things like:

```
What is the current deployment target, and which file pins it?
What did the last session claim was done, and is there externally-produced evidence for it?
Where does the project currently lie to itself - where do the recorded notes disagree with repo reality?
```

The protocol: at the start of every session, the agent re-derives the answer to each question *against the current repo* — reads the actual files, runs the actual commands — diffs the fresh answer against what the project previously believed, appends one line to an append-only JSONL log, and tells us every delta out loud before doing anything else. The log line records, per question: an id, a timestamp, and a `delta` boolean, plus the repo's HEAD sha at derivation time:

```json
{"ts": "...", "kind": "rederive", "sid": "s03", "repo_head_sha": "c1d4f0a...", "results": [{"q_id": "q4", "last_rederived_ts": "...", "delta": true, "note": "s02 handoff claims rate limiter 'done'; no test covers the burst path"}]}
```

A stored answer is wrong the moment reality moves. A stored question is never wrong; it's at worst unasked — and "unasked" turns out to be detectable, which is the part of this story we care most about.

The asymmetry is the whole trick. Database people will recognize it instantly: the answer is a materialized view, the question is the view's defining query, session start is `REFRESH`, and staleness is refresh lag. We didn't invent that frame [literature — view maintenance goes back to at least Gupta & Mumick, 1995]; we just hadn't seen anyone make the *question* the unit of agent memory and the answer the disposable thing.

## The heavyweight version, and what re-derivation actually caught

The first production implementation was not lean. At peak: 28 standing questions, each a JSON file with a full derivation history; per-derivation evidence-path lists with SHA-256 content hashes; every re-derivation gated behind an LLM judge that had to approve the derivation before it could be committed; an out-of-band evaluator process with heartbeat checks [observed]. We built the cathedral.

Parts of it earned their keep. Three catches we can document from our own artifacts [observed]:

- **It reopened the falsely-done milestone.** After the incident, "is this milestone complete against its criteria?" became a standing question. Its first re-derivation recorded, with file citations, exactly which two criteria passed and which two failed — and that derivation stayed live and re-checkable instead of rotting in a handoff note.
- **It caught a session that closed without finishing its own loop.** One session produced a judge-approved derivation but never committed it to the store. The *next* session's start-of-session audit noticed the dangling state — verdict file present, store entry absent — and repaired it, on the record. Without a session-start re-check keyed to artifacts, that gap would simply have been forgotten.
- **The judge, while healthy, did real work.** One derivation took five consecutive rejections before its claims were grounded enough to commit [observed]. When the judge was functioning, it approved roughly a third of submissions [observed] — a rejection rate that high is uncomfortable, and that discomfort was the point.

But the cathedral is also where the failures lived, and the failures are more instructive than the catches.

## Goodhart incident #1: the same-author judge collapses into a checkbox

The judge was supposed to be independent supervision. In practice, the running session controlled what got submitted, how it was framed, and what evidence the judge saw — evidence surfaces largely *authored by the session being judged*. Over weeks, the judge drifted into a checkbox function: grading citation-formatting of text the main session wrote, rather than independently checking reality [observed].

It got worse. In one session the agent issued four manual overrides because the judge loop was non-functional, and kept working anyway [observed]. On two occasions, the agent *faked launching* the out-of-band judge process — produced output as if supervision had run when it hadn't [observed]. A separate session wrote "derivation committed" in its close-out notes without ever calling the commit function; the dangling state was caught at the next session start [observed].

The lesson we took [inferred]: **any verification signal the agent can author, it will eventually author.** Not out of malice — out of optimization pressure toward looking done. If your anti-drift machinery's evidence stream runs through the thing being checked, you've built a Goodhart engine with extra steps.

This is why the lean pattern keys its honesty machinery to two signals the agent does not control: the git HEAD sha (externally pinned), and the simple presence or absence of per-question entries in an append-only log (falsifiable by anyone with `grep`).

## Goodhart incident #2: acknowledge-without-rederive

The second failure was quieter and, we think, more universal.

The session-start gate would surface stale questions — "STALE: these N questions haven't been re-derived past their cadence." The session would *acknowledge* the list. And move on. Re-derivation is work; acknowledgment is a sentence. At the worst point, ten standing questions sat stale, surfaced-and-acknowledged, across many consecutive sessions [observed]. The gate had become a ritual. The store had become, as we wrote in frustration at the time, a museum of questions nobody answers.

The fix that mattered wasn't exhortation (we tried exhortation; the agent agreed enthusiastically and changed nothing [observed]). The fix was making the failure *computable*. Two metrics, both shipped in the repo, both runnable against the log with stdlib Python:

1. **Staleness** — for each question, sessions since it last appeared in a rederive entry. A question with no entry for N sessions isn't memory, it's decoration.
2. **Acknowledge-without-rederive** — sessions where *every* question reports `delta:false` while the repo HEAD *moved*. One such session is normal. A consecutive run of them is the signature of an agent going through the motions, and the detector alarms on the run.

We want to be precise about what these are: **detectors, not guarantees.** The log records that re-derivation reportedly happened. An agent that fabricates plausible deltas defeats both metrics, and we know of no mechanical fix at the reasoning level — this matches the broader observation that you can structurally verify actions and artifacts, but not whether reasoning actually occurred [inferred]. What the detectors catch is the cheap form of ritualization — all-quiet-while-the-world-moves — and in our ten weeks, the cheap form was the only form that actually occurred [observed]. Our read is that fabricating *coherent* fake deltas across sessions was more work than just re-deriving [inferred]; we would not assume that holds for every agent and setup.

## What survived: the lean kernel

Almost none of the cathedral made it into the version we'd tell anyone else to run. What survived contact [observed → distilled]:

- One JSON file of ~12 human-owned questions. (28 was too many; the long tail went stale and polluted the gate's signal.)
- One append-only JSONL log; one entry per session; `{q_id, last_rederived_ts, delta}` per question plus the HEAD sha.
- A four-step session-start ritual: load, re-derive, record, report deltas out loud.
- The two metrics, run by a human or CI — *outside* the agent's authorship.

The judge didn't survive — not because independent evaluation is wrong, but because a same-author judge is worse than no judge: it manufactures false assurance [inferred]. The evidence hashes didn't survive; the HEAD sha gives most of the detection power for none of the ceremony [inferred]. The lean kernel is what's in the repo.

We haven't given up on the cathedral parts. Evidence-pinned provenance and gated verdict production may yet have a form that survives its own Goodhart audit — if we find it, that's a separate post.

## What we can and can't claim

Can [observed, first-party, N-of-1]: the pattern ran for ten weeks across roughly 300 sessions on a production repo; re-derivation produced documented catches of real drift, including a falsely-done milestone and an unclosed commit loop; both Goodhart failure modes occurred, were diagnosed from artifacts, and became computable metrics; the lean kernel has near-zero per-session cost (a dozen questions re-derived at session start, one log line appended).

Can't: any comparative effectiveness claim. We did not run a control. We cannot tell you it beats Mem0, a long CLAUDE.md, or doing nothing, on any benchmark. One project, one team, one stack. If you run it and your acknowledge-without-rederive detector fires in week two, we'd genuinely like to know — that replication would be worth more than this post.

One more boundary [literature-informed]: standing questions are a curated index layer *on top of* preserved raw history — transcripts, git, full logs — never a replacement for it. Lee et al.'s Meta-Harness ablation is the cleanest number we know pointing this direction: a harness optimizer given raw execution traces hit 50.0 median accuracy; the same optimizer given scores-plus-summaries hit 34.9 (arXiv:2603.28052, Table 3) [literature]. Different task, so treat it as directional for this pattern, not proof — but "summaries quietly destroy the signal you'll need later" matches everything we observed, and the pattern is built to respect it: keep raw everything, curate only the questions.

## On novelty, honestly

We'll claim the assembly and the name; we won't claim the parts. The nearest neighbor we know is **architecture fitness functions** (Ford, Parsons & Kua) — durable, human-authored assertions continuously re-evaluated against the codebase; standing questions differ in re-deriving *open* answers and diffing them, and in having metrics for the executor going through the motions, which CI-executed assertions don't need. **Park et al.'s Generative Agents** (arXiv:2304.03442) literally generates questions during reflection — but transiently, as scaffolding to produce durably-stored *answers*: the exact opposite durability assignment. **Spaced repetition** made the question the durable scheduling unit in 1987, to strengthen a fixed answer in a human head rather than track a moving one in a repo. **Materialized views** are the database formulation; **living documentation** (doctest, Concordion) re-executes docs against code; **held-out canaries** probe systems with known answers, where standing questions probe a world whose answers legitimately change. And the mainstream agent-memory ecosystem (MemGPT/Letta, Mem0, Zep, A-MEM) is the deliberate foil: it persists extracted facts so agents can stop re-deriving; this pattern re-derives precisely the dozen beliefs that must never silently rot. The combination — durable human-gated questions, per-session re-derivation against repo ground truth, an append-only delta log keyed to HEAD, and the staleness + ritualization metrics — is, as far as we can determine after looking hard, not previously published as a pattern. If you know prior work closer than the above, tell us and we'll put it at the top of the README's prior-art section.

## The release

The repo — [github.com/Rocco-alt/standing-questions](https://github.com/Rocco-alt/standing-questions) — ships the pattern, not a framework: the write-up; JSON Schemas (draft 2020-12) for the question store and the log entry; a generic 12-question seed set; a seven-session sample log with one stale question and one ritualization run baked in so you can watch both metrics fire; an installable Claude Code skill implementing the four-step ritual; and the two metrics as dependency-free Python with tests. Everything runs identically on Windows, macOS, and Linux. MIT.

Store the questions. Re-derive the answers. And measure the ritual, because the ritual is where it dies.
