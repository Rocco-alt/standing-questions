#!/usr/bin/env python3
"""Per-question staleness: sessions since each standing question was last re-derived.

A standing question only protects you while it is actually being re-derived.
This metric counts, for every question, how many sessions have passed since the
last rederive-log entry that included it. A question nobody has re-derived in
N sessions is decoration, not memory.

Reads the append-only rederive log (one JSON object per line, kind="rederive",
see schema/rederive_entry.schema.json). Lines with any other "kind" are
skipped, so the log may be shared with other entry kinds.

Usage:
    python metrics/staleness.py <rederive_log.jsonl> [--questions <standing_questions.json>] [--threshold N]

Example (from the repo root):
    python metrics/staleness.py examples/rederive_log.jsonl --questions examples/standing_questions.json

Definitions:
  - Entries are grouped into sessions by "sid" (file order = session order;
    multiple entries with the same sid, e.g. mid-session re-grounding passes,
    count as one session).
  - staleness = number of sessions strictly after the last session that
    re-derived the question. 0 means "re-derived in the latest session".
  - A question that never appears has staleness = total session count.
  - Exit code 1 if any question's staleness exceeds --threshold (default 5),
    else 0. CI-friendly.

Stdlib only. No dependencies. This file is deliberately self-contained so it
can be copied into a project as-is (the small parsing overlap with
acknowledge_without_rederive.py is intentional).
"""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_THRESHOLD = 5


def load_entries(log_path):
    """Read a JSONL file and return the entries whose kind is 'rederive'."""
    entries = []
    try:
        f = open(log_path, encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"{log_path}: cannot read file: {exc}")
    with f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{log_path}:{line_no}: invalid JSON: {exc}")
            if obj.get("kind") != "rederive":
                continue
            entries.append(obj)
    return entries


def sessions_from_entries(entries):
    """Collapse entries into an ordered list of sessions (one per sid).

    Each session is {"sid", "ts", "repo_head_sha", "rederived": {q_id: last_rederived_ts}}.
    File order determines session order; repeated sids merge into the first
    occurrence (union of re-derived questions, last entry's HEAD/ts win).
    """
    sessions = []
    by_sid = {}
    for e in entries:
        sid = e.get("sid")
        if sid in by_sid:
            s = by_sid[sid]
        else:
            s = {"sid": sid, "ts": e.get("ts"), "repo_head_sha": e.get("repo_head_sha"), "rederived": {}}
            by_sid[sid] = s
            sessions.append(s)
        s["ts"] = e.get("ts", s["ts"])
        s["repo_head_sha"] = e.get("repo_head_sha", s["repo_head_sha"])
        for r in e.get("results", []):
            s["rederived"][r["q_id"]] = r.get("last_rederived_ts", e.get("ts"))
    return sessions


def compute_staleness(sessions, question_ids=None):
    """Return {q_id: {"staleness": int, "last_sid": str|None, "last_rederived_ts": str|None}}.

    If question_ids is None, the universe of questions is every q_id that ever
    appears in the log (in first-seen order). Passing the active ids from the
    standing-questions store is better: it also catches questions that have
    NEVER been re-derived.
    """
    if question_ids is None:
        question_ids = []
        seen = set()
        for s in sessions:
            for q in s["rederived"]:
                if q not in seen:
                    seen.add(q)
                    question_ids.append(q)
    total = len(sessions)
    report = {}
    for q in question_ids:
        last_idx = None
        last_ts = None
        last_sid = None
        for i, s in enumerate(sessions):
            if q in s["rederived"]:
                last_idx = i
                last_ts = s["rederived"][q]
                last_sid = s["sid"]
        staleness = total if last_idx is None else total - 1 - last_idx
        report[q] = {"staleness": staleness, "last_sid": last_sid, "last_rederived_ts": last_ts}
    return report


def load_active_question_ids(questions_path):
    """Return the ids of active questions from a standing-questions store file."""
    try:
        raw = Path(questions_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"{questions_path}: cannot read file: {exc}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{questions_path}: invalid JSON: {exc}")
    return [q["id"] for q in data.get("questions", []) if q.get("status", "active") == "active"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Per-question staleness over a rederive log.")
    parser.add_argument("log", help="path to the rederive log (JSONL)")
    parser.add_argument("--questions", help="path to standing_questions.json (recommended: catches never-rederived questions)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help=f"flag questions with staleness greater than this (default {DEFAULT_THRESHOLD})")
    args = parser.parse_args(argv)

    entries = load_entries(args.log)
    sessions = sessions_from_entries(entries)
    if not sessions:
        print("no rederive entries found - nothing to measure (that is itself a finding)")
        return 1
    question_ids = load_active_question_ids(args.questions) if args.questions else None
    report = compute_staleness(sessions, question_ids)

    print(f"sessions in log: {len(sessions)} (latest: {sessions[-1]['sid']})")
    flagged = []
    width = max(len(q) for q in report)
    for q, info in report.items():
        last = info["last_sid"] if info["last_sid"] is not None else "never"
        line = f"  {q:<{width}}  staleness={info['staleness']:>3}  last_rederived={last}"
        if info["staleness"] > args.threshold:
            line += f"   <-- STALE (over threshold {args.threshold})"
            flagged.append(q)
        print(line)
    if flagged:
        print(f"FLAGGED: {len(flagged)} question(s) over staleness threshold {args.threshold}: {', '.join(flagged)}")
        return 1
    print(f"OK: all questions within staleness threshold {args.threshold}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
