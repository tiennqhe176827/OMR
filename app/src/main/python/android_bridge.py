"""Camera adapter. The omr package is shared verbatim with the desktop engine."""
import json
import time
import zipfile
from pathlib import Path
import cv2
import numpy as np
from omr.errors import OMRError
from omr.marker_detection import detect_markers, select_corner_markers
from omr.quality import assess_quality
from omr.pipeline import process_exam_sheet
from omr.grading import AnswerKeyStore, PROFILES, grade_with_store, numeric
from camera_tracker import SheetTracker

TEMPLATE = str(Path(__file__).parent / 'templates/real_sheet_experimental.json')
SHEET_TEMPLATES = {
    'current': TEMPLATE,
    'cv1239': str(Path(__file__).parent / 'templates/thpt_cv1239_4digit.json'),
}

def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)

def camera_image(data, width, height, rotation):
    """Packed Y plane from CameraX, rotated clockwise into display orientation."""
    gray = np.frombuffer(data, np.uint8).reshape(height, width)
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Invalid camera rotation')
    # Own the pixels even for rotation=0: CameraX/Java may reuse its buffer.
    return np.rot90(gray, -(rotation // 90)).copy(order='C')

class Scanner:
    AUTO_CAPTURE_DELAY_NS = 2_000_000_000
    MAX_CORNER_DRIFT = .025

    def __init__(self, directory, template_path=TEMPLATE):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.template_path = template_path
        self.reset()

    def reset(self, preserve_diagnostic=False):
        self.done = False
        self.last_frame = None
        self.last_report = None
        self.captured_frame = None
        self.captured_report = None
        self.capture_info = {}
        self.cancel_pending_capture()
        if not preserve_diagnostic:
            self.failure_frame = None
            self.failure_report = None
            self.failure_metrics = None
        self.tracker = SheetTracker()

    def set_template(self, template_id):
        if template_id not in SHEET_TEMPLATES:
            raise ValueError('Mẫu phiếu không hợp lệ.')
        from omr.template_loader import load_template
        path = SHEET_TEMPLATES[template_id]
        load_template(path)
        self.template_path = path
        self.reset()
        return template_id

    def cancel_pending_capture(self):
        self.pending_since_ns = None
        self.pending_corners = None
        self.pending_last_ns = None

    def _automatic_capture_ready(self, report, timestamp_ns):
        if not report.get('capture_ready') or report.get('corners') is None:
            self.cancel_pending_capture()
            return False
        now = timestamp_ns if timestamp_ns is not None else time.monotonic_ns()
        corners = np.asarray(report['corners'], dtype=np.float32)
        restart = (self.pending_since_ns is None or self.pending_corners.shape != corners.shape
                   or now <= self.pending_last_ns
                   or now - self.pending_last_ns > 1_500_000_000
                   or np.max(np.linalg.norm(corners - self.pending_corners, axis=1)) > self.MAX_CORNER_DRIFT)
        if restart:
            self.pending_since_ns = now
            self.pending_corners = corners.copy()
        self.pending_last_ns = now
        remaining = max(0, self.AUTO_CAPTURE_DELAY_NS - (now - self.pending_since_ns))
        report['capture_ready'] = remaining == 0
        report['capture_wait_ms'] = (remaining + 999_999) // 1_000_000
        if remaining:
            report.update(state='stabilizing',
                          message=f'Đã nhận diện giấy. Giữ yên máy… chụp sau {(remaining + 999_999_999) // 1_000_000_000} giây.')
        return remaining == 0

    def observe_and_capture(self, data, width, height, rotation, capture_timestamp_ns=None, manual=False):
        """Wait for a stable sheet for two seconds, then retain the latest frame.

        No subsequent camera exposure, focus request or JPEG callback is needed.
        Later camera buffers cannot overwrite the retained pixels.
        """
        if self.captured_report is not None:
            return dumps(self.captured_report)
        began = time.perf_counter()
        report = json.loads(self._detect_only(data, width, height, rotation, capture_timestamp_ns))
        automatic_ready = self._automatic_capture_ready(report, capture_timestamp_ns)
        if (automatic_ready or manual) and self.last_frame is not None:
            self.captured_frame = self.last_frame
            self.captured_frame.setflags(write=False)
            frozen_ms = (time.perf_counter() - began) * 1000
            h, w = self.captured_frame.shape
            self.capture_info = {'source': 'retained_camera_y', 'width': w, 'height': h,
                                 'timestamp_ns': capture_timestamp_ns,
                                 'detection_to_retained_ms': round(frozen_ms, 2),
                                 'trigger': 'manual' if manual else 'automatic'}
            preview = cv2.resize(self.captured_frame, (min(w, 720), round(h * min(w, 720) / w)))
            path = self.directory / 'capture_preview.jpg'
            ok, encoded = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                raise RuntimeError('Không tạo được ảnh xem trước.')
            path.write_bytes(encoded.tobytes())
            self.capture_info['ready_for_ui_ms'] = round((time.perf_counter() - began) * 1000, 2)
            report.update(state='captured', preview_path=str(path), capture=self.capture_info,
                          message='Đã giữ ảnh — bạn có thể di chuyển máy. Đang đọc phiếu…')
            self.captured_report = report
            (self.directory / 'capture-latency.json').write_text(dumps(self.capture_info), encoding='utf-8')
        self.last_report = report
        return dumps(report)

    def analyze_captured(self):
        if self.captured_frame is None:
            raise ValueError('Chưa giữ được ảnh camera.')
        return self._run_omr(cv2.cvtColor(self.captured_frame, cv2.COLOR_GRAY2BGR),
                             manual=self.capture_info.get('trigger') == 'manual')

    def detect_only(self, data, width, height, rotation, capture_timestamp_ns=None):
        """Find a paper outline or its four markers in the live Y frame.
        observe_and_capture applies the stabilization wait before retaining pixels.
        """
        payload = self._detect_only(data, width, height, rotation, capture_timestamp_ns)
        self.last_report = json.loads(payload)
        return payload

    def analyze_file(self, file_path, manual=False):
        """Nhận ảnh tĩnh đã chụp (JPEG), chạy toàn bộ OMR pipeline.
        Đây là hàm được gọi SAU KHI Kotlin đã chụp ảnh tĩnh bằng ImageCapture.
        """
        image = cv2.imread(file_path)
        if image is None:
            return dumps({'state': 'searching', 'message': 'Không đọc được ảnh đã chụp.'})
        self.last_frame = image
        return self._run_omr(image, manual=manual)

    def analyze_last(self, manual=False):
        """Fallback: xử lý OMR trên last_frame nếu không có ImageCapture."""
        if self.last_frame is None:
            return dumps({'state': 'searching', 'message': 'Không có frame.'})
        frame = self.last_frame
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        return self._run_omr(frame, manual=manual)

    # Legacy: giữ lại để không break các test cũ
    def analyze(self, data, width, height, rotation, manual=False):
        payload = self._analyze(data, width, height, rotation, manual)
        self.last_report = json.loads(payload)
        return payload

    def _detect_only(self, data, width, height, rotation, capture_timestamp_ns=None):
        if self.done:
            return dumps({'state': 'done'})
        gray = camera_image(data, width, height, rotation)
        self.last_frame = gray
        report = self.tracker.observe(gray, capture_timestamp_ns)
        return dumps(report)

    def _run_omr(self, image, manual=False):
        """Chạy toàn bộ pipeline OMR trên ảnh tĩnh BGR. Trả về JSON result."""
        result, artifacts = process_exam_sheet(image, self.template_path, debug=True)
        if result['status'] != 'ok':
            failure = {
                'state': 'searching',
                'message': {
                    'orientation_failed': 'Thấy 4 góc nhưng bố cục chưa khớp mẫu. Kiểm tra đúng mẫu phiếu.',
                    'alignment_failed': 'Thấy 4 góc nhưng lệch chưa khớp. Giữ giấy phẳng.',
                    'image_too_blurry': 'Ảnh bị mờ. Giữ yên rồi thử lại.',
                    'marker_detection_failed': 'Mất marker khi chụp. Giữ yên và tránh vùng bị lóa.',
                }.get(result.get('error', {}).get('code', ''), 'Chưa đọc được phiếu: ' + str(result.get('error', ''))),
                'error': result.get('error')
            }
            self.last_report = failure
            self.failure_frame = image
            self.failure_report = failure
            self.failure_metrics = self.tracker.last_metrics.copy()
            return dumps(failure)
        self.failure_frame = None
        self.failure_report = None
        self.failure_metrics = None
        stamp = str(time.time_ns())
        result['capture'] = {'source': 'camera', 'id': stamp,
                             'stable_frames': self.tracker.stable_frames,
                             'trigger': 'manual' if manual else 'automatic', **self.capture_info}
        scan_dir = self.directory / 'scans'
        scan_dir.mkdir(exist_ok=True)
        grid_path = scan_dir / f'{stamp}_grid.png'
        image_path = scan_dir / f'{stamp}.png'
        for path, frame in ((image_path, image), (grid_path, artifacts.get('13_grid_overlay', image))):
            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            ok, encoded = cv2.imencode('.png', frame)
            if ok:
                path.write_bytes(encoded.tobytes())
        (scan_dir / f'{stamp}.json').write_text(dumps(result), encoding='utf-8')
        self.done = True
        self.last_report = {'state': 'result', 'capture_id': stamp}
        return dumps({'state': 'result', 'result': result, 'grid_path': str(grid_path)})

    # _analyze giữ lại cho legacy / fallback
    def _analyze(self, data, width, height, rotation, manual=False):
        payload = self._detect_only(data, width, height, rotation)
        return payload


    def diagnostic(self, device_json='{}'):
        frame = self.failure_frame if self.failure_frame is not None else self.last_frame
        if frame is None:
            raise ValueError('Chưa có khung camera để kiểm tra. Mở camera trước.')
        from omr.visualization import draw_markers
        from omr.template_loader import load_template
        report = {'app_version': '1.17', 'device': json.loads(device_json), 'capture': self.capture_info,
                  'opencv': cv2.__version__, 'quality': assess_quality(frame),
                  'last_response': self.failure_report if self.failure_report is not None else self.last_report,
                  'tracking': self.failure_metrics if self.failure_metrics is not None else self.tracker.last_metrics}
        template = load_template(self.template_path).data
        report['template'] = {k: template[k] for k in ('template_id', 'calibration_status', 'reference_sha256')}
        markers, corners = [], None
        try:
            markers = detect_markers(frame)
            corners = select_corner_markers(markers, frame.shape)
        except OMRError as exc:
            report['marker_error'] = {'code': exc.code, 'message': str(exc)}
        report['markers'] = [marker.to_dict() for marker in markers]
        report['corners'] = corners.tolist() if corners is not None else None
        
        frame_color = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame
        overlay = draw_markers(frame_color, markers, corners)
        destination = self.directory / 'camera-diagnostic.zip'
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('diagnostic.json', dumps(report))
            for name, frame in (('camera.png', frame_color), ('markers.png', overlay)):
                ok, encoded = cv2.imencode('.png', frame)
                if not ok:
                    raise RuntimeError('Không lưu được khung chẩn đoán')
                archive.writestr(name, encoded.tobytes())
        return str(destination)

def key_skeleton(exam, subject, code, track):
    n1, n2, n3, _ = PROFILES[subject]
    return dumps({'schema_version': 1, 'exam': exam, 'subject': subject, 'code': code,
                  'track': track if subject == 'Tin học' else '', 'tf_questions': list(range(1, n2 + 1)),
                  'phan_1': {str(q): '' for q in range(1, n1 + 1)},
                  'phan_2': {str(q): dict.fromkeys('abcd', '') for q in range(1, n2 + 1)},
                  'phan_3': {str(q): '' for q in range(1, n3 + 1)}})

def save_key(directory, text, revision):
    key = json.loads(text)
    return dumps(AnswerKeyStore(Path(directory) / 'answer_keys').save(key, None if revision < 0 else revision))

def validate_key_json(text):
    from omr.grading import validate_key
    return dumps(validate_key(json.loads(text)))

def load_key(directory, exam, subject, code, track):
    return dumps(AnswerKeyStore(Path(directory) / 'answer_keys').load(exam, subject, code, track))

def correct_result(directory, text, section, question, answers_json, exam, subject, track):
    result = json.loads(text)
    if section not in ('phan_1', 'phan_2', 'phan_3') or question not in result.get(section, {}):
        raise ValueError('Câu cần sửa không hợp lệ.')
    answers = json.loads(answers_json)
    if not isinstance(answers, dict) or not answers:
        raise ValueError('Hãy nhập bài làm trên phiếu.')
    targets = result[section][question]
    allowed = set('abcd') if section == 'phan_2' else {'value'}
    if not set(answers) <= allowed:
        raise ValueError('Ô cần sửa không hợp lệ.')
    for item, value in answers.items():
        decision = targets[item] if section == 'phan_2' else targets
        if decision.get('status') == 'ok' and decision.get('source') != 'manual':
            raise ValueError('Chỉ nhập tay các câu chưa rõ hoặc đã nhập tay.')
        if section == 'phan_1' and value not in ('A', 'B', 'C', 'D'):
            raise ValueError('Chọn A, B, C hoặc D.')
        if section == 'phan_2' and value not in ('Dung', 'Sai'):
            raise ValueError('Chọn Đúng hoặc Sai.')
        if section == 'phan_3':
            numeric(value)
            value = value.strip()
        if 'original_recognition' not in decision:
            decision['original_recognition'] = json.loads(dumps(decision))
        decision.update(status='ok', source='manual', confidence=1.0)
        decision['value' if section == 'phan_3' else 'answer'] = value
        if section != 'phan_3':
            decision['selected'] = value
    return grade_result(directory, dumps(result), exam, subject, track)


def grade_result(directory, text, exam, subject, track):
    result = json.loads(text)
    result.pop('grading', None)
    try:
        result['grading'] = grade_with_store(result, AnswerKeyStore(Path(directory) / 'answer_keys'), exam, subject, track)
    except ValueError as exc:
        result['grading'] = {'status': 'unavailable', 'message': str(exc)}
    capture_id = result.get('capture', {}).get('id', '')
    if capture_id.isdigit():
        _save_graded_image(directory, capture_id, result)
        (Path(directory) / 'scans' / f'{capture_id}.json').write_text(dumps(result), encoding='utf-8')
    return dumps(result)


def _save_graded_image(directory, capture_id, result):
    from omr.local_warp import warp_with_mesh
    from omr.perspective import warp_sheet
    from omr.visualization import draw_graded_answers
    folder = Path(directory) / 'scans'
    image = cv2.imread(str(folder / f'{capture_id}.png'))
    alignment = result.get('alignment', {})
    if image is None or not alignment.get('canonical_size'):
        return
    size = tuple(alignment['canonical_size'][k] for k in ('width', 'height'))
    mesh = alignment.get('local_mesh')
    matrix = np.asarray(alignment['original_to_pre_refinement'] if mesh else alignment['original_to_canonical'])
    warped = warp_with_mesh(image, matrix, size, mesh) if mesh else warp_sheet(image, matrix, size)
    canvas = draw_graded_answers(warped, result)
    ok, encoded = cv2.imencode('.png', canvas)
    if not ok:
        raise ValueError('Không tạo được ảnh chấm điểm.')
    path = folder / f'{capture_id}_graded.png'
    path.write_bytes(encoded.tobytes())
    result['graded_image_path'] = str(path)
