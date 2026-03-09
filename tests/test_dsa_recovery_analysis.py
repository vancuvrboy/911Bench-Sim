from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tests.harness.analyze_dsa_recovery import analyze


class TestDSARecoveryAnalysis(unittest.TestCase):
    def test_profile_mean_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.csv"
            with p.open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["scenario", "qa_score", "dsa_profile"])
                w.writeheader()
                w.writerow({"scenario": "a", "qa_score": "70", "dsa_profile": "baseline"})
                w.writerow({"scenario": "b", "qa_score": "80", "dsa_profile": "baseline"})
                w.writerow({"scenario": "c", "qa_score": "85", "dsa_profile": "candidate"})
                w.writerow({"scenario": "d", "qa_score": "95", "dsa_profile": "candidate"})
            out = analyze(p, baseline_profile="baseline")
            self.assertAlmostEqual(out["profiles"]["baseline"]["mean_qa"], 75.0)
            self.assertAlmostEqual(out["profiles"]["candidate"]["mean_qa"], 90.0)
            self.assertAlmostEqual(out["mean_delta_vs_baseline"]["candidate"], 15.0)


if __name__ == "__main__":
    unittest.main()
