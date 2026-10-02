import json
import unittest
from test_camera_bridge import ROOT
from omr.pipeline import process_exam_sheet


class ReportedUnclearTests(unittest.TestCase):
    def test_clear_zero_with_empty_trailing_columns(self):
        folder = ROOT / "output/unclear-1.12"
        ident = "1790828902990925068"
        photo = folder / (ident + ".png")
        if not photo.exists():
            self.skipTest("Reported camera scan is not available")
        result, _ = process_exam_sheet(str(photo), str(ROOT / "app/src/main/python/templates/real_sheet_experimental.json"))
        self.assertEqual(result["status"], "ok", result.get("error"))
        self.assertEqual([result["phan_3"][str(q)]["value"] for q in range(1, 7)],
                         ["2108", "0", "0,31", "1", "4", "9"])
        self.assertEqual([c["status"] for c in result["phan_3"]["2"]["columns"]],
                         ["ok", "blank", "blank", "blank"])
        previous = json.loads((folder / (ident + ".json")).read_bytes())
        for key, old in previous["groups"].items():
            if old["status"] == "ok":
                self.assertEqual((result["groups"][key]["status"], result["groups"][key]["selected"]),
                                 ("ok", old["selected"]), key)
