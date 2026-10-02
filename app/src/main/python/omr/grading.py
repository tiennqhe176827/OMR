"""Saved answer keys and deterministic scoring (all arithmetic in hundredths)."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


# Counts follow the subject table requested by the project owner.
PROFILES = {
    'Toán': (12, 4, 6, 50),
    'Ngoại ngữ': (40, 0, 0, 0),
    'Vật lí': (18, 4, 6, 25),
    'Hóa học': (18, 4, 6, 25),
    'Sinh học': (18, 4, 6, 25),
    'Lịch sử': (24, 4, 0, 0),
    'Địa lí': (24, 4, 0, 0),
    'GDKT&PL': (24, 4, 0, 0),
    'Công nghệ': (24, 4, 0, 0),
    'Tin học': (24, 4, 0, 0),
}
TRACKS = ('Khoa học máy tính', 'Tin học ứng dụng')
TF_POINTS = (0, 10, 25, 50, 100)


def numeric(value):
    """Exact numeric equality: decimal comma/dot accepted, no rounding or exponent."""
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', value.strip()):
        raise ValueError('Trả lời ngắn phải là số, ví dụ -1,5 hoặc 2.75.')
    return Decimal(value.strip().replace(',', '.'))


def identity(exam, subject, code, track=''):
    if not isinstance(exam, str) or not exam.strip():
        raise ValueError('Hãy nhập tên bài kiểm tra / kỳ thi.')
    if subject not in PROFILES:
        raise ValueError('Môn học không hợp lệ.')
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{1,16}', code):
        raise ValueError('Mã đề phải là chuỗi chữ số; giữ nguyên số 0 đầu mã.')
    if subject == 'Tin học' and track not in TRACKS:
        raise ValueError('Chọn định hướng Tin học trước khi lưu hoặc chấm.')
    return (exam.strip(), subject, code, track if subject == 'Tin học' else '')


def validate_key(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Định dạng đáp án không được hỗ trợ.')
    key = deepcopy(data)
    key['exam'], key['subject'], key['code'], key['track'] = identity(
        key.get('exam'), key.get('subject'), key.get('code'), key.get('track', ''))
    n1, n2, n3, _ = PROFILES[key['subject']]
    questions = key.get('tf_questions')
    limit = 6 if key['subject'] == 'Tin học' else n2
    if (not isinstance(questions, list) or len(questions) != n2
            or any(type(q) is not int or not 1 <= q <= limit for q in questions)
            or len(set(questions)) != n2):
        raise ValueError(f'Chọn đúng {n2} câu Đúng/Sai khác nhau trong khoảng 1–{limit}.')
    if key['subject'] != 'Tin học' and questions != list(range(1, n2+1)):
        raise ValueError('Danh sách câu Đúng/Sai không đúng cấu trúc môn.')
    expected = {
        'phan_1': [str(i) for i in range(1, n1+1)],
        'phan_2': [str(i) for i in questions],
        'phan_3': [str(i) for i in range(1, n3+1)],
    }
    for section, ids in expected.items():
        answers = key.get(section)
        if not isinstance(answers, dict) or set(answers) != set(ids):
            raise ValueError(f'{section}: cần nhập đủ và đúng các câu {", ".join(ids)}.')
        for q, answer in answers.items():
            if section == 'phan_1' and answer not in ('A', 'B', 'C', 'D'):
                raise ValueError(f'Phần I câu {q}: chọn A, B, C hoặc D.')
            if section == 'phan_2' and (not isinstance(answer, dict) or set(answer) != set('abcd')
                    or any(a not in ('Dung', 'Sai') for a in answer.values())):
                raise ValueError(f'Phần II câu {q}: nhập đủ Đúng/Sai cho a, b, c, d.')
            if section == 'phan_3':
                numeric(answer)
                answers[q] = answer.strip()
    return key


class AnswerKeyStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def path(self, exam, subject, code, track=''):
        ident = identity(exam, subject, code, track)
        digest = hashlib.sha256(json.dumps(ident, ensure_ascii=False).encode('utf-8')).hexdigest()
        return self.directory/f'{digest}.json'

    def load(self, exam, subject, code, track=''):
        path = self.path(exam, subject, code, track)
        if not path.exists():
            return None
        key = validate_key(json.loads(path.read_text(encoding='utf-8')))
        if identity(key['exam'], key['subject'], key['code'], key['track']) != identity(exam, subject, code, track):
            raise ValueError('Nội dung file đáp án không khớp tên lưu trữ.')
        return key

    def list_keys(self):
        # Corrupt keys are surfaced; never silently replaced by another code.
        return [validate_key(json.loads(p.read_text(encoding='utf-8')))
                for p in sorted(self.directory.glob('*.json'))]

    def save(self, data, expected_revision=None):
        key = validate_key(data)
        path = self.path(key['exam'], key['subject'], key['code'], key['track'])
        current = self.load(key['exam'], key['subject'], key['code'], key['track'])
        if current and current.get('revision') != expected_revision:
            raise ValueError('Mã đề đã tồn tại hoặc vừa được sửa. Hãy tải lại đáp án trước khi cập nhật.')
        key['revision'] = (current.get('revision', 0) if current else 0) + 1
        key['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.directory, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(key, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return key


def compare(decision, expected, short=False):
    """Return a correctness interval; unreadable data is not an assumed wrong answer."""
    decision = decision if isinstance(decision, dict) else {}
    status = decision.get('status', 'missing')
    actual = decision.get('value' if short else 'answer')
    if status in ('blank', 'multiple', 'invalid'):
        low = high = 0
    elif status != 'ok':
        low, high = 0, 1
    else:
        try:
            if short:
                correct = numeric(actual) == numeric(expected)
            else:
                if actual not in ('A', 'B', 'C', 'D', 'Dung', 'Sai'):
                    raise ValueError('Missing decoded answer')
                correct = actual == expected
            low = high = int(correct)
        except (ValueError, TypeError):
            low, high, status = 0, 1, 'ambiguous'
    return {'actual': actual, 'expected': expected, 'status': status,
            'correct_min': low, 'correct_max': high}


def grade(result, data):
    key = validate_key(data)
    if result.get('status') != 'ok':
        raise ValueError('Phiếu chưa đọc thành công, không thể chấm.')
    code = result.get('student', {}).get('ma_de', {})
    if code.get('status') != 'ok' or code.get('value') != key['code']:
        raise ValueError('Mã đề nhận diện chưa rõ hoặc không khớp đáp án; không tự chọn mã khác.')
    sections, details = {}, []
    _, _, _, short_points = PROFILES[key['subject']]
    for section in ('phan_1', 'phan_2', 'phan_3'):
        low_total = high_total = maximum = 0
        for q, expected in key[section].items():
            actual = result.get(section, {}).get(q)
            if section == 'phan_2':
                statements = {s: compare((actual or {}).get(s), expected[s]) for s in 'abcd'}
                low = TF_POINTS[sum(a['correct_min'] for a in statements.values())]
                high = TF_POINTS[sum(a['correct_max'] for a in statements.values())]
                item, points = {'statements': statements}, 100
            else:
                item = compare(actual, expected, section == 'phan_3')
                points = short_points if section == 'phan_3' else 25
                low, high = points*item['correct_min'], points*item['correct_max']
            item.update(section=section, question=q, score_min=low/100, score_max=high/100, maximum=points/100)
            details.append(item)
            low_total += low
            high_total += high
            maximum += points
        sections[section] = {'score_min': low_total/100, 'score_max': high_total/100, 'maximum': maximum/100}
    low = round(sum(s['score_min'] for s in sections.values()), 2)
    high = round(sum(s['score_max'] for s in sections.values()), 2)
    reasons = []
    if low != high:
        reasons.append('Có câu chưa rõ hoặc thiếu dữ liệu nhận diện; điểm hiển thị là khoảng có thể đạt.')
    if result.get('quality', {}).get('overall_status') != 'ok' or result.get('warnings'):
        reasons.append('Chất lượng / template OMR yêu cầu kiểm tra lại ảnh gốc.')
    snapshot = json.dumps(key, ensure_ascii=False, sort_keys=True)
    return {'status': 'review_required' if reasons else 'graded',
            'score': low if not reasons else None, 'score_min': low, 'score_max': high, 'maximum': 10,
            'review_reasons': reasons, 'sections': sections, 'details': details,
            'answer_key': key, 'answer_key_sha256': hashlib.sha256(snapshot.encode('utf-8')).hexdigest(),
            'graded_at': datetime.now(timezone.utc).isoformat(),
            'policy': 'THPT_user_profiles_v1; TF=0/0.10/0.25/0.50/1; numeric_exact',
            'ignored_questions': {s: sorted(set(result.get(s, {}))-set(key[s])) for s in sections}}


def grade_with_store(result, store, exam, subject, track=''):
    if result.get('status') != 'ok':
        raise ValueError('Phiếu chưa đọc thành công.')
    code = result.get('student', {}).get('ma_de', {})
    if code.get('status') != 'ok' or not code.get('value'):
        raise ValueError('Chưa đọc rõ mã đề. Kiểm tra vùng mã đề trên ảnh.')
    key = store.load(exam, subject, code['value'], track)
    if key is None:
        raise ValueError(f'Chưa lưu đáp án {subject} — mã {code["value"]} trong bài “{exam}”.')
    return grade(result, key)
