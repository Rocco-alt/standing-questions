#!/usr/bin/env python3
"""Acknowledge-without-rederive detector: the ritualization signature.

The known failure mode of any session-start ritual is going through the
motions: the agent writes the rederive entry, reports delta:false on every
question, and starts the day's work without having actually re-derived
anything. One such session is unremarkable. A run of them - every question
reporting "no change" while the repo's HEAD keeps moving - is the signature
of a gate that has ritualized.

This detector flags exactly that signature: sessions whose rederive entry
reports delta:false for ALL questions despite repo_head_sha differing from
the previous session's. All-delta:false with an UNCHANGED HEAD is fine
(nothing moved, so nothing should have changed) and is not flagged.

This is a detector, not a guarantee: an agent that fabricates plausible
deltas defeats it. It catches the cheap, observed form of ritualization,
which in practice is the common one.

Reads the same append-only rederive log as staleness.py. Lines whose "kind"
is not "rederive" are skipped.

Usage:
    python metrics/acknowledge_without_rederive.py <rederive_log.jsonl> [--max-consecutive N]

Example (from the repo root):
    python metrics/acknowledge_without_rederive.py examples/rederive_log.jsonl

Exit code 1 when the longest run of suspicious sessions exceeds
--max-consecutive (default 2, i.e. 3 consecutive suspicious sessions alarm),
else 0. CI-friendly.

Stdlib only. No dependencies. Deliberately self-contained (the small parsing
overlap with staleness.py is intentional).
"""

import argparse
import json
import sys

DEFAULT_MAX_CONSECUTIVE = 2


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

    Each session is {"sid", "ts", "repo_head_sha", "deltas": {q_id: bool}}.
    File order determines session order; repeated sids merge into the first
    occurrence (later deltas for the same question win).
    """
    sessions = []
    by_sid = {}
    for e in entries:
        sid = e.get("sid")
        if sid in by_sid:
            s = by_sid[sid]
        else:
            s = {"sid": sid, "ts": e.get("ts"), "repo_head_sha": e.get("repo_head_sha"), "deltas": {}}
            by_sid[sid] = s
            sessions.append(s)
        s["ts"] = e.get("ts", s["ts"])
        s["repo_head_sha"] = e.get("repo_head_sha", s["repo_head_sha"])
        for r in e.get("results", []):
            s["deltas"][r["q_id"]] = bool(r.get("delta"))
    return sessions


def detect(sessions):
    """Per-session verdicts: [{"sid", "suspicious": bool, "reason": str}].

    A session is suspicious when its HEAD differs from the previous session's
    AND it re-derived at least one question AND every reported delta is false.
    The first session is never suspicious (no prior HEAD to compare).
    """
    verdicts = []
    prev = None
    for s in sessions:
        suspicious = False
        if prev is None:
            reason = "first session in log - no prior HEAD to compare"
        else:
            head_moved = s["repo_head_sha"] != prev["repo_head_sha"]
            deltas = list(s["deltas"].values())
            all_false = bool(deltas) and not any(deltas)
            if head_moved and all_false:
                suspicious = True
                reason = "HEAD moved since previous session but every re-derived question reported delta:false"
            elif not head_moved and all_false:
                reason = "all delta:false but HEAD unchanged - consistent"
            elif any(deltas):
                changed = sorted(q for q, d in s["deltas"].items() if d)
                reason = f"deltas reported: {', '.join(changed)}"
            else:
                reason = "no results recorded"
        verdicts.append({"sid": s["sid"], "suspicious": suspicious, "reason": reason})
        prev = s
    return verdicts


def longest_suspicious_run(verdicts):
    """Length of the longest run of consecutive suspicious sessions."""
    best = 0
    current = 0
    for v in verdicts:
        current = current + 1 if v["suspicious"] else 0
        best = max(best, current)
    return best


def main(argv=None):
    parser = argparse.ArgumentParser(description="Detect the acknowledge-without-rederive (ritualization) signature in a rederive log.")
    parser.add_argument("log", help="path to the rederive log (JSONL)")
    parser.add_argument("--max-consecutive", type=int, default=DEFAULT_MAX_CONSECUTIVE, help=f"alarm when more than this many consecutive sessions are suspicious (default {DEFAULT_MAX_CONSECUTIVE})")
    args = parser.parse_args(argv)

    entries = load_entries(args.log)
    sessions = sessions_from_entries(entries)
    if not sessions:
        print("no rederive entries found - nothing to measure (that is itself a finding)")
        return 1
    verdicts = detect(sessions)

    for v in verdicts:
        tag = "SUSPECT" if v["suspicious"] else "ok     "
        print(f"  {tag}  {v['sid']}: {v['reason']}")
    run = longest_suspicious_run(verdicts)
    suspicious_total = sum(1 for v in verdicts if v["suspicious"])
    print(f"suspicious sessions: {suspicious_total}/{len(verdicts)}; longest consecutive run: {run}")
    if run > args.max_consecutive:
        print(f"ALARM: {run} consecutive sessions reported no deltas while HEAD kept moving (threshold {args.max_consecutive}) - the gate is likely ritualizing; spot-check the next session's rederivation by hand")
        return 1
    print("OK: no ritualization signature over threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
