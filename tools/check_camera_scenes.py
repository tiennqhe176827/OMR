"""Offline camera-like scenes from the supplied real sheet, not a device test."""
import json
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/src/main/python'))
from android_bridge import TEMPLATE, camera_image
from omr.io import read_image
from omr.pipeline import process_exam_sheet


def scenes(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    yield 'camera_gray', gray
    yield 'camera_limited_y', (16 + gray.astype(float) * (219 / 255)).astype(np.uint8)
    for paper_height in (1000, 1400):
        paper = cv2.resize(gray, (round(gray.shape[1] * paper_height / gray.shape[0]), paper_height))
        h, w = paper.shape
        for background in (25, 120):
            scene = np.full((h + 220, w + 240), background, np.uint8)
            scene[100:100+h, 120:120+w] = paper
            yield f'paper_{paper_height}_background_{background}', scene
            shade = np.linspace(.65, 1., scene.shape[1])[None, :]
            yield f'paper_{paper_height}_background_{background}_shadow', (scene * shade).astype(np.uint8)
    h, w = gray.shape
    source = np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
    target = np.float32([[100, 55], [w+30, 110], [w+90, h+90], [60, h+40]])
    warped = cv2.warpPerspective(gray, cv2.getPerspectiveTransform(source, target), (w+180, h+180), borderValue=25)
    yield 'perspective_dark_table', warped
    yield 'perspective_shadow', (warped * np.linspace(.65, 1., warped.shape[1])[None, :]).astype(np.uint8)


if __name__ == '__main__':
    image = read_image(ROOT.parent / 'cdtd/omr_system/input/real_sheet.png')
    baseline, _ = process_exam_sheet(image, TEMPLATE)
    if baseline['status'] != 'ok':
        raise RuntimeError(baseline.get('error'))
    report = []
    for name, gray in scenes(image):
        frame = camera_image(gray.tobytes(), gray.shape[1], gray.shape[0], 0)
        result, _ = process_exam_sheet(frame, TEMPLATE)
        mismatches = [gid for gid, expected in baseline['groups'].items()
                      if any(result.get('groups', {}).get(gid, {}).get(field) != expected[field]
                             for field in ('status', 'selected'))]
        row = {'scene': name, 'status': result['status'], 'error': result.get('error'),
               'mismatches_from_baseline': mismatches, 'elapsed_seconds': result['elapsed_seconds']}
        report.append(row)
        print(name, row['status'], row['error'], 'mismatches:', len(mismatches), flush=True)
    (ROOT / 'camera-scenes-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    sys.exit(0 if all(row['status'] == 'ok' and not row['mismatches_from_baseline'] for row in report) else 1)
