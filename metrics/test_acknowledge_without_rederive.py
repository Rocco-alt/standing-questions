#!/usr/bin/env python3
"""Tests for acknowledge_without_rederive.py. Run from anywhere:

    python metrics/test_acknowledge_without_rederive.py

Stdlib only (unittest + tempfile).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import acknowledge_without_rederive as awr


def entry(sid, sha, deltas, ts="2026-05-01T00:00:00Z"):
    """deltas: {q_id: bool}"""
    return {
        "ts": ts,
        "kind": "rederive",
        "sid": sid,
        "repo_head_sha": sha,
        "results": [{"q_id": q, "last_rederived_ts": ts, "delta": d} for q, d in deltas.items()],
    }


class TestDetector(unittest.TestCase):
    def detect(self, entries):
        return awr.detect(awr.sessions_from_entries(entries))

    def test_head_moved_all_false_is_suspicious(self):
        verdicts = self.detect([
            entry("s1", "aaa1111", {"q1": False, "q2": True}),
            entry("s2", "bbb2222", {"q1": False, "q2": False}),
        ])
        self.assertFalse(verdicts[0]["suspicious"])  # first session: no prior HEAD
        self.assertTrue(verdicts[1]["suspicious"])

    def test_head_unchanged_all_false_is_consistent(self):
        verdicts = self.detect([
            entry("s1", "aaa1111", {"q1": False}),
            entry("s2", "aaa1111", {"q1": False}),  # no commits since s1
        ])
        self.assertFalse(verdicts[1]["suspicious"])

    def test_any_delta_true_clears_the_session(self):
        verdicts = self.detect([
            entry("s1", "aaa1111", {"q1": False}),
            entry("s2", "bbb2222", {"q1": True}),
        ])
        self.assertFalse(verdicts[1]["suspicious"])

    def test_longest_run_and_alarm_threshold(self):
        entries = [
            entry("s1", "sha0000", {"q1": False}),
            entry("s2", "sha1111", {"q1": False}),  # suspicious 1
            entry("s3", "sha2222", {"q1": False}),  # suspicious 2
            entry("s4", "sha3333", {"q1": False}),  # suspicious 3
        ]
        verdicts = self.detect(entries)
        self.assertEqual(awr.longest_suspicious_run(verdicts), 3)

    def test_run_resets_on_clean_session(self):
        entries = [
            entry("s1", "sha0000", {"q1": False}),
            entry("s2", "sha1111", {"q1": False}),  # suspicious
            entry("s3", "sha2222", {"q1": True}),   # clean - resets run
            entry("s4", "sha3333", {"q1": False}),  # suspicious
        ]
        verdicts = self.detect(entries)
        self.assertEqual(awr.longest_suspicious_run(verdicts), 1)

    def test_cli_exit_codes(self):
        entries = [
            entry("s1", "sha0000", {"q1": False}),
            entry("s2", "sha1111", {"q1": False}),
            entry("s3", "sha2222", {"q1": False}),
            entry("s4", "sha3333", {"q1": False}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.jsonl"
            path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
            # longest run = 3 -> alarm with default max-consecutive 2 (exit 1)
            self.assertEqual(awr.main([str(path)]), 1)
            # raising the threshold to 3 silences the alarm (exit 0)
            self.assertEqual(awr.main([str(path), "--max-consecutive", "3"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
