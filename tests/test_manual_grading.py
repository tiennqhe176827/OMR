import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from test_camera_bridge import create_fixture
from android_bridge import Scanner, correct_result, grade_result, key_skeleton, save_key


class ManualGradingTests(unittest.TestCase):
    def test_corrections_persist_regrade_and_color_image(self):
        with tempfile.TemporaryDirectory() as directory:
            template, photo, _ = create_fixture(Path(directory) / "fixture")
            scanner = Scanner(directory, str(template))
            result = json.loads(scanner.analyze_file(str(photo)))["result"]
            key = json.loads(key_skeleton("Thi", "Toán", "107", ""))
            key["phan_1"] = {q: "A" for q in key["phan_1"]}
            key["phan_2"] = {q: dict.fromkeys("abcd", "Dung") for q in key["phan_2"]}
            key["phan_3"] = {q: "2.5" for q in key["phan_3"]}
            save_key(directory, json.dumps(key), -1)
            result["phan_1"]["1"].update(status="ambiguous", answer=None)
            result["phan_2"]["1"]["a"].update(status="ambiguous", answer=None)
            result["phan_3"]["2"].update(status="ambiguous", value=None)
            for section, q, answers in [("phan_1", "1", {"value": "B"}),
                                        ("phan_2", "1", {"a": "Dung"}),
                                        ("phan_3", "2", {"value": "2,50"})]:
                result = json.loads(correct_result(directory, json.dumps(result), section, q,
                                   json.dumps(answers), "Thi", "Toán", ""))
            details = {(d["section"], d["question"]): d for d in result["grading"]["details"]}
            self.assertEqual(details[("phan_1", "1")]["correct_max"], 0)
            self.assertEqual(details[("phan_2", "1")]["statements"]["a"]["correct_min"], 1)
            self.assertEqual(details[("phan_3", "2")]["correct_min"], 1)
            self.assertEqual(result["phan_3"]["2"]["original_recognition"]["status"], "ambiguous")
            saved = json.loads((Path(directory) / "scans" / (result["capture"]["id"] + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(saved["phan_3"]["2"]["value"], "2,50")
            image = cv2.imread(result["graded_image_path"])
            self.assertTrue(np.any(np.all(image == (0, 180, 0), axis=2)))
            self.assertTrue(np.any(np.all(image == (0, 0, 230), axis=2)))
            with self.assertRaises(ValueError):
                correct_result(directory, json.dumps(result), "phan_3", "2", '{"value":"abc"}', "Thi", "Toán", "")
            with self.assertRaises(ValueError):
                correct_result(directory, json.dumps(result), "phan_1", "2", '{"value":"B"}', "Thi", "Toán", "")
            # Manual answers remain editable, and regrading uses the edited value.
            result = json.loads(correct_result(directory, json.dumps(result), "phan_3", "2", '{"value":"3"}', "Thi", "Toán", ""))
            self.assertEqual(result["phan_3"]["2"]["original_recognition"]["status"], "ambiguous")
            missing = json.loads(grade_result(directory, json.dumps(result), "Other exam", "Toán", ""))
            self.assertEqual(missing["grading"]["status"], "unavailable")
            gray = cv2.imread(missing["graded_image_path"])
            self.assertFalse(np.any(np.all(gray == (0, 180, 0), axis=2)))
            self.assertFalse(np.any(np.all(gray == (0, 0, 230), axis=2)))
