import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'cdtd/omr_system'))
sys.path.insert(0, str(ROOT / 'app/src/main/python'))
import cv2
import numpy as np
from android_bridge import Scanner, camera_image, save_key, load_key, grade_result, key_skeleton
from camera_tracker import SheetTracker
from omr.io import read_image
from tools.synthetic_fixture import create_fixture


class CameraBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.template, cls.path, cls.truth = create_fixture(Path(cls.temp.name))
        cls.image = read_image(cls.path)
        cls.gray = cv2.cvtColor(cls.image, cv2.COLOR_BGR2GRAY)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_rotation_and_unsigned_y_plane(self):
        source = np.array([[0, 128, 255], [1, 129, 254]], np.uint8)
        for rotation in (0, 90, 180, 270):
            np.testing.assert_array_equal(camera_image(source.tobytes(), 3, 2, rotation),
                                          np.rot90(source, -rotation // 90))

    def test_live_lock_then_full_resolution_omr(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            h, w = self.gray.shape
            first = json.loads(scanner.detect_only(self.gray.tobytes(), w, h, 0))
            self.assertEqual(first['state'], 'locked')
            self.assertEqual(first['corner_count'], 4)
            self.assertTrue(first['capture_ready'])
            capture = Path(directory) / 'capture.jpg'
            self.assertTrue(cv2.imwrite(str(capture), self.image, [cv2.IMWRITE_JPEG_QUALITY, 97]))
            output = json.loads(scanner.analyze_file(str(capture)))
            self.assertEqual(output['state'], 'result', output.get('message'))
            self.assertEqual(output['result']['student']['ma_de']['value'], '107')
            for group, expected in self.truth.items():
                actual = output['result']['groups'][group]
                self.assertEqual((actual['status'], actual['selected']),
                                 (expected['status'], expected['selected']), group)
            key = json.loads(key_skeleton('Thi', 'Ngoại ngữ', '107', ''))
            key['phan_1'] = {str(q): output['result']['phan_1'][str(q)].get('answer') or 'A'
                             for q in range(1, 41)}
            save_key(directory, json.dumps(key), -1)
            graded = json.loads(grade_result(directory, json.dumps(output['result']), 'Thi', 'Ngoại ngữ', ''))
            self.assertNotEqual(graded['grading']['status'], 'unavailable')
            self.assertGreater(graded['grading']['score_max'], 0)
            self.assertTrue(Path(output['grid_path']).exists())
            self.assertEqual(json.loads(scanner.detect_only(self.gray.tobytes(), w, h, 0))['state'], 'done')

    def test_no_stale_detection_after_paper_is_removed(self):
        tracker = SheetTracker()
        frame = cv2.resize(self.gray, (640, 896))
        self.assertTrue(tracker.observe(frame)['capture_ready'])
        blank = tracker.observe(np.full_like(frame, 255))
        self.assertFalse(blank['capture_ready'])
        self.assertIsNone(blank['corners'])
        self.assertTrue(tracker.observe(frame)['capture_ready'])

    def test_retained_full_resolution_frame_survives_camera_movement(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            h, w = self.gray.shape
            pixels = bytearray(self.gray.tobytes())
            for timestamp in (0, 1_000_000_000):
                waiting = json.loads(scanner.observe_and_capture(pixels, w, h, 0, timestamp))
                self.assertEqual(waiting['state'], 'stabilizing')
                self.assertIsNone(scanner.captured_frame)
            first = json.loads(scanner.observe_and_capture(pixels, w, h, 0, 2_000_000_000))
            self.assertEqual(first['state'], 'captured')
            self.assertEqual((first['capture']['width'], first['capture']['height']), (w, h))
            pixels[:] = bytes([255]) * len(pixels)
            second = json.loads(scanner.observe_and_capture(pixels, w, h, 0, 999999))
            self.assertEqual(first, second)
            np.testing.assert_array_equal(scanner.captured_frame, self.gray)
            output = json.loads(scanner.analyze_captured())
            self.assertEqual(output['state'], 'result', output.get('message'))
            self.assertEqual(output['result']['capture']['source'], 'retained_camera_y')
            for group, expected in self.truth.items():
                actual = output['result']['groups'][group]
                self.assertEqual((actual['status'], actual['selected']),
                                 (expected['status'], expected['selected']), group)
            scanner.reset()
            self.assertNotEqual(json.loads(scanner.observe_and_capture(pixels, w, h, 0))['state'], 'captured')

    def test_countdown_restarts_on_motion_loss_pause_or_long_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            corners = np.array([[.1, .1], [.9, .1], [.9, .9], [.1, .9]])
            def observe(seconds, points=corners, ready=True):
                report = {'capture_ready': ready, 'corners': points.tolist() if ready else None}
                result = scanner._automatic_capture_ready(report, int(seconds * 1_000_000_000))
                return result, report
            self.assertFalse(observe(0)[0])
            self.assertEqual(observe(1)[1]['capture_wait_ms'], 1000)
            self.assertEqual(observe(2, corners + .05)[1]['capture_wait_ms'], 2000)
            self.assertFalse(observe(3, ready=False)[0])
            self.assertEqual(observe(4)[1]['capture_wait_ms'], 2000)
            scanner.cancel_pending_capture()
            self.assertEqual(observe(5)[1]['capture_wait_ms'], 2000)
            self.assertEqual(observe(8)[1]['capture_wait_ms'], 2000)
            self.assertFalse(observe(9)[0])
            self.assertTrue(observe(10)[0])

    def test_manual_capture_bypasses_countdown(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            h, w = self.gray.shape
            report = json.loads(scanner.observe_and_capture(self.gray.tobytes(), w, h, 0, 0, True))
            self.assertEqual(report['state'], 'captured')
            self.assertEqual(report['capture']['trigger'], 'manual')

    def test_first_corner_updates_progress_without_capture(self):
        frame = np.full((896, 640), 255, np.uint8)
        target = SheetTracker._guide_targets(frame.shape)[0] * [frame.shape[1], frame.shape[0]]
        x, y = target.astype(int)
        cv2.rectangle(frame, (x-8, y-8), (x+8, y+8), 0, -1)
        report = SheetTracker().observe(frame)
        self.assertEqual(report['state'], 'searching')
        self.assertEqual(report['corner_count'], 1)
        self.assertFalse(report['capture_ready'])

    def test_retained_camera_limited_luma_range_reads_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            luma = np.round(16 + self.gray.astype(np.float32) * (219 / 255)).astype(np.uint8)
            h, w = luma.shape
            for timestamp in (0, 1_000_000_000, 2_000_000_000):
                report = json.loads(scanner.observe_and_capture(luma.tobytes(), w, h, 0, timestamp))
            self.assertEqual(report['state'], 'captured')
            output = json.loads(scanner.analyze_captured())
            self.assertEqual(output['state'], 'result', output.get('message'))
            for group, expected in self.truth.items():
                actual = output['result']['groups'][group]
                self.assertEqual((actual['status'], actual['selected']),
                                 (expected['status'], expected['selected']), group)

    def test_distant_sheet_prompts_closer_then_captures_first_close_frame(self):
        frame = np.full((896, 640), 30, np.uint8)
        small_sheet = cv2.resize(self.gray, (370, 518))
        frame[189:707, 135:505] = small_sheet
        report = SheetTracker().observe(frame)
        self.assertEqual(report['state'], 'locked')
        self.assertEqual(report['corner_count'], 4)
        self.assertFalse(report['capture_ready'])
        self.assertTrue(report['too_small'])
        self.assertEqual(report['metrics']['capture_blocker'], 'move_closer')
        self.assertIn(report['metrics']['capture_source'], ('paper', 'markers'))
        self.assertLess(report['metrics']['marker_side_at_960px'], 13)
        tracker = SheetTracker()
        tracker.observe(frame)
        self.assertTrue(tracker.observe(cv2.resize(self.gray, (640, 896)))['capture_ready'])

    def test_handheld_drift_does_not_delay_capture(self):
        frame = cv2.resize(self.gray, (640, 896))
        tracker = SheetTracker()
        self.assertTrue(tracker.observe(frame)['capture_ready'])
        shifted = cv2.warpAffine(frame, np.float32([[1, 0, 20], [0, 1, 0]]),
                                 (640, 896), borderValue=255)
        report = tracker.observe(shifted)
        self.assertTrue(report['capture_ready'])

    def test_paper_outline_captures_without_waiting_for_four_markers(self):
        frame = np.full((896, 640), 50, np.uint8)
        cv2.rectangle(frame, (25, 30), (615, 865), 215, -1)
        for y in range(170, 730, 28):
            cv2.line(frame, (180, y), (460, y), 105, 2)
        report = SheetTracker().observe(frame)
        self.assertEqual(report['state'], 'page_detected')
        self.assertEqual(report['corner_count'], 0)
        self.assertEqual(report['metrics']['capture_source'], 'paper')
        self.assertTrue(report['capture_ready'])
        self.assertEqual(len(report['corners']), 4)

    def test_blank_or_clipped_paper_does_not_trigger_outline_capture(self):
        blank = np.full((896, 640), 50, np.uint8)
        cv2.rectangle(blank, (140, 120), (500, 760), 215, -1)
        self.assertFalse(SheetTracker().observe(blank)['capture_ready'])
        clipped = blank.copy()
        cv2.rectangle(clipped, (140, 120), (500, 760), 50, -1)
        cv2.rectangle(clipped, (0, 120), (380, 760), 215, -1)
        for y in range(170, 730, 28):
            cv2.line(clipped, (40, y), (340, y), 105, 2)
        self.assertFalse(SheetTracker().observe(clipped)['capture_ready'])

    def test_manual_still_rejects_bad_input_and_records_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            blank_path = Path(directory) / 'blank.jpg'
            cv2.imwrite(str(blank_path), np.full_like(self.image, 255))
            self.assertEqual(json.loads(scanner.analyze_file(str(blank_path), True))['state'], 'searching')
            result = json.loads(scanner.analyze_file(str(self.path), True))
            self.assertEqual(result['state'], 'result')
            self.assertEqual(result['result']['capture']['trigger'], 'manual')

    def test_diagnostic_includes_failure_and_tracker_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(directory, str(self.template))
            h, w = self.gray.shape
            scanner.detect_only(self.gray.tobytes(), w, h, 0)
            error = {'status': 'error', 'error': {'code': 'alignment_failed', 'message': 'Missing markers'}}
            with patch('android_bridge.process_exam_sheet', return_value=(error, {})):
                response = json.loads(scanner.analyze_file(str(self.path)))
            self.assertEqual(response['error'], error['error'])
            scanner.reset(preserve_diagnostic=True)
            scanner.detect_only(np.full_like(self.gray, 255).tobytes(), w, h, 0)
            with zipfile.ZipFile(scanner.diagnostic('{"model":"test"}')) as archive:
                report = json.loads(archive.read('diagnostic.json'))
                self.assertEqual(report['last_response']['error'], error['error'])
                self.assertIn('total_ms', report['tracking'])

    def test_key_revision_and_grading_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            key = json.loads(key_skeleton('Thi', 'Ngoại ngữ', '001', ''))
            key['phan_1'] = {str(q): 'A' for q in range(1, 41)}
            saved = json.loads(save_key(directory, json.dumps(key), -1))
            self.assertEqual(saved['revision'], 1)
            self.assertEqual(json.loads(load_key(directory, 'Thi', 'Ngoại ngữ', '001', ''))['code'], '001')
            with self.assertRaises(ValueError):
                save_key(directory, json.dumps(key), -1)
            result = {'status': 'ok', 'quality': {'overall_status': 'ok'},
                      'student': {'ma_de': {'status': 'ok', 'value': '001'}},
                      'phan_1': {str(q): {'status': 'ok', 'answer': 'A'} for q in range(1, 41)}}
            graded = json.loads(grade_result(directory, json.dumps(result), 'Thi', 'Ngoại ngữ', ''))
            self.assertEqual(graded['grading']['score'], 10)
            result['student']['ma_de']['value'] = '1'
            self.assertEqual(json.loads(grade_result(directory, json.dumps(result), 'Thi', 'Ngoại ngữ', ''))['grading']['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
