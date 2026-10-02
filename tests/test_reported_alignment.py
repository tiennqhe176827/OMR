import json
import unittest
from pathlib import Path
from test_camera_bridge import ROOT
from omr.pipeline import process_exam_sheet


class ReportedAlignmentTests(unittest.TestCase):
    def test_local_drift_is_refined_even_when_marker_error_is_below_threshold(self):
        photo = ROOT / "output/alignment-1.11/camera.png"
        if not photo.exists():
            self.skipTest("Reported camera diagnostic is not available")
        result, _ = process_exam_sheet(str(photo), str(ROOT / "app/src/main/python/templates/real_sheet_experimental.json"))
        self.assertEqual(result["status"], "ok", result.get("error"))
        alignment = result["alignment"]
        self.assertLess(alignment["error_before_px"], alignment["threshold_px"])
        self.assertIn("piecewise_affine_markers", alignment["refinement_methods"])
        self.assertEqual(alignment["auxiliary_matched"], 26)
        self.assertLessEqual(max(alignment["local_block_errors_px"].values()), 3.5)
