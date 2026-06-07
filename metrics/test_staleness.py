#!/usr/bin/env python3
"""Tests for staleness.py. Run from anywhere:

    python metrics/test_staleness.py

Stdlib only (unittest + tempfile).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import staleness


def entry(sid, sha, q_ids, ts="2026-05-01T00:00:00Z", kind="rederive"):
    return {
        "ts": ts,
        "kind": kind,
        "sid": sid,
        "repo_head_sha": sha,
        "results": [{"q_id": q, "last_rederived_ts": ts, "delta": False} for q in q_ids],
    }


def write_log(tmpdir, entries):
    path = Path(tmpdir) / "log.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


class TestStaleness(unittest.TestCase):
    def test_counts_sessions_since_last_rederive(self):
        entries = [
            entry("s1", "aaa1111", ["q1", "q2"]),
            entry("s2", "bbb2222", ["q1"]),
            entry("s3", "ccc3333", ["q1"]),
        ]
        sessions = staleness.sessions_from_entries(entries)
        report = staleness.compute_staleness(sessions)
        self.assertEqual(report["q1"]["staleness"], 0)  # re-derived in latest session
        self.assertEqual(report["q2"]["staleness"], 2)  # last seen in s1, two sessions since
        self.assertEqual(report["q2"]["last_sid"], "s1")

    def test_never_rederived_question_gets_total_session_count(self):
        entries = [entry("s1", "aaa1111", ["q1"]), entry("s2", "bbb2222", ["q1"])]
        sessions = staleness.sessions_from_entries(entries)
        report = staleness.compute_staleness(sessions, question_ids=["q1", "q9"])
        self.assertEqual(report["q9"]["staleness"], 2)
        self.assertIsNone(report["q9"]["last_sid"])

    def test_repeated_sid_counts_as_one_session(self):
        # A mid-session re-grounding pass reuses the sid; it must not inflate counts.
        entries = [
            entry("s1", "aaa1111", ["q1", "q2"]),
            entry("s2", "bbb2222", ["q1"]),
            entry("s2", "bbb2222", ["q2"]),  # same session, second pass
        ]
        sessions = staleness.sessions_from_entries(entries)
        self.assertEqual(len(sessions), 2)
        report = staleness.compute_staleness(sessions)
        self.assertEqual(report["q2"]["staleness"], 0)

    def test_non_rederive_lines_are_skipped(self):
        entries = [
            entry("s1", "aaa1111", ["q1"]),
            {"ts": "2026-05-02T00:00:00Z", "kind": "decision", "sid": "s1", "what": "unrelated"},
            entry("s2", "bbb2222", ["q1"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_log(tmp, entries)
            loaded = staleness.load_entries(path)
        self.assertEqual(len(loaded), 2)
        self.assertTrue(all(e["kind"] == "rederive" for e in loaded))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # q2 last re-derived 2 sessions ago -> threshold 1 flags it (exit 1),
            # threshold 5 does not (exit 0).
            path = write_log(tmp, [
                entry("s1", "aaa1111", ["q1", "q2"]),
                entry("s2", "bbb2222", ["q1"]),
                entry("s3", "ccc3333", ["q1"]),
            ])
            self.assertEqual(staleness.main([str(path), "--threshold", "1"]), 1)
            self.assertEqual(staleness.main([str(path), "--threshold", "5"]), 0)

    def test_active_question_filter_skips_retired(self):
        store = {
            "_schema": "standing_questions/v1",
            "questions": [
                {"id": "q1", "q": "?", "importance": 3},
                {"id": "q2", "q": "?", "importance": 1, "status": "retired"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            qpath = Path(tmp) / "questions.json"
            qpath.write_text(json.dumps(store), encoding="utf-8")
            self.assertEqual(staleness.load_active_question_ids(qpath), ["q1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
