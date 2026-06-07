# Installing the skill (Claude Code)

The skill lives in [`standing-questions/SKILL.md`](standing-questions/SKILL.md). Claude Code discovers skills by directory name, so the folder must be named `standing-questions` (it is — just copy it whole).

## Option A — install for one project (recommended)

From your project root:

**macOS / Linux (bash):**

```bash
mkdir -p .claude/skills
cp -r path/to/standing-questions/skill/standing-questions .claude/skills/
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force .claude\skills | Out-Null
Copy-Item -Recurse path\to\standing-questions\skill\standing-questions .claude\skills\
```

## Option B — install for all your projects

Same copy, but into `~/.claude/skills/` instead of `.claude/skills/`:

**macOS / Linux (bash):**

```bash
mkdir -p ~/.claude/skills
cp -r path/to/standing-questions/skill/standing-questions ~/.claude/skills/
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\skills | Out-Null
Copy-Item -Recurse path\to\standing-questions\skill\standing-questions $env:USERPROFILE\.claude\skills\
```

## Seed the question store

The skill expects `context/standing_questions.json` in your project. Start from the example set and edit it to point at your project's actual ground truth:

**macOS / Linux (bash):**

```bash
mkdir -p context
cp path/to/standing-questions/examples/standing_questions.json context/
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force context | Out-Null
Copy-Item path\to\standing-questions\examples\standing_questions.json context\
```

## Use it

Type `/standing-questions` at the start of a session, or just ask Claude to "run the standing questions" — the description lets Claude invoke it on its own when a session starts in a repo that has the store. The first run creates `context/rederive_log.jsonl`; every later run appends one line.

To make the ritual harder to skip, add one line to your project's `CLAUDE.md`:

```markdown
- At session start, run /standing-questions before any other work.
```

Note what that line is and is not: it is advisory, not enforcement. The agent can still skip it or go through the motions — which is exactly why the log exists and why you should run the two metrics (see [`metrics/`](../metrics/)) from time to time, or wire them into CI:

```
python metrics/staleness.py context/rederive_log.jsonl --questions context/standing_questions.json
python metrics/acknowledge_without_rederive.py context/rederive_log.jsonl
```

Both exit non-zero when they find the failure they look for, so they slot into any CI as-is.

## Other harnesses

Nothing here is Claude-specific. The skill file is four numbered steps of plain English plus two JSON files — port it to any agent harness that can read files, run `git rev-parse HEAD`, and append a line of JSON to a log.
