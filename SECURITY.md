# Security

## What the skill is, mechanically

`skill/standing-questions/SKILL.md` is a static markdown instruction file — about 40 lines, readable in two minutes. It contains no executable code, no install scripts, and no network access. At runtime it directs an agent to: read two project-local files (`context/standing_questions.json`, `context/rederive_log.jsonl`), run `git rev-parse HEAD`, append one line of JSON to the log, and report deltas out loud. That is the entire tool surface it asks for. Review it before installing, as you would any third-party code.

## Threat model

Mapped against the OWASP Top 10 for LLM Applications (LLM01: Prompt Injection) and OWASP Agentic ASI01 (Agent Goal Hijacking):

- **The skill file itself.** Static, and pinned by your install copy — it changes only when you re-copy it. The supply-chain risk lives in the copy step: install from a source you trust, and read the diff when you update ([CHANGELOG.md](CHANGELOG.md) records what changed).
- **The question store.** An injection surface in principle: the skill directs the agent to read it and act on it. The protocol's hard rule — question text is human-owned, agents never edit it — exists for integrity, but it also means a hostile question store implies a hostile repo; an attacker who can write to your repo has better options than your question store.
- **The rederive log.** Agent-authored, so the most plausible injection channel (a poisoned `note` read back at session start). Two structural mitigations: the skill reads only the last 2 entries, and Step 2 explicitly forbids deriving answers from log content — the log is for diffing; ground truth comes from the repo. This is a mitigation, not a guarantee.
- **Secrets.** The skill's hard rules forbid quoting secrets into the log, because the log is typically committed and never pruned.

## What we can and can't claim

No certification for "safe from prompt injection" exists — for this artifact or any other (as of June 2026). What exists: risk taxonomies (OWASP LLM01/ASI01), organization-level process standards (ISO/IEC 42001, NIST AI RMF), and scanners. Scanners are detectors, not guarantees — the same epistemic status as this repo's own metrics. One practical note from scanning this very skill: generic injection scanners are tuned for untrusted input and can flag instruction files simply for being dense with imperatives — weigh any scanner finding against your own two-minute read of the file.

- Scanned with [Snyk Skill Inspector](https://labs.snyk.io/experiments/skill-scan/) on 2026-06-07: **no issues found**, 9/9 checks passed (prompt injection, malicious code, suspicious downloads, improper credential handling, secret detection, third-party content exposure, unverifiable dependencies, direct money access, modifying system services). If you modify the skill, re-scan your copy.
- Authored against Anthropic's skill-writing guidance.

## Reporting

Open a GitHub issue for non-sensitive reports. For anything sensitive, email raj@soggl.com.
