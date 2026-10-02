"""Live-path marker detection under realistic user mistakes.

Guards the regression where holding the phone a little further away made the
sheet smaller than min_quad_area_fraction and detection returned nothing at all.
Not a device test: it drives the same code path as the camera overlay using the
frames in video-check/ plus synthetic placements.
"""
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/src/main/python'))
from android_bridge import fast_detect_corners, validate_geometry

FRAME = ROOT / 'video-check/frame0.jpg'


def place(sheet, shape, background=60):
    canvas = np.full(shape, background, np.uint8)
    h, w = shape
    y0 = max(0, (h-sheet.shape[0])//2)
    x0 = max(0, (w-sheet.shape[1])//2)
    canvas[y0:y0+sheet.shape[0], x0:x0+sheet.shape[1]] = sheet
    return canvas


def cases(image):
    h, w = image.shape
    yield 'as captured', image, True
    for scale in (0.85, 0.7, 0.65, 0.55):
        small = cv2.resize(image, (round(w*scale), round(h*scale)), interpolation=cv2.INTER_AREA)
        yield f'sheet at {int(scale*100)}% scale', place(small, image.shape), True
    # Below roughly 10% of the frame the sheet is too small to read, so the
    # pipeline refuses it on purpose. Keep one case pinning that floor.
    tiny = cv2.resize(image, (round(w*0.45), round(h*0.45)), interpolation=cv2.INTER_AREA)
    yield 'sheet at 45% scale (must refuse)', place(tiny, image.shape), False
    for dx, dy in ((-70, 0), (70, 0), (0, -90), (0, 90), (-60, -70)):
        matrix = np.float32([[1, 0, dx], [0, 1, dy]])
        yield f'shifted {dx},{dy}', cv2.warpAffine(image, matrix, (w, h), borderValue=60), True
    for angle in (3, 6, 10, -8, 15):
        matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
        yield f'rotated {angle} deg', cv2.warpAffine(image, matrix, (w, h), borderValue=60), True
    for gain in (1.25, 1.5, 0.7, 0.5):
        lit = np.clip(image.astype(float)*gain, 0, 255).astype(np.uint8)
        yield f'exposure gain {gain}', lit, True


if __name__ == '__main__':
    image = cv2.imread(str(FRAME), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise SystemExit(f'missing {FRAME}')
    problems = []
    planned = list(cases(image))
    for label, frame, must_detect in planned:
        corners = fast_detect_corners(frame)
        detected = corners is not None and validate_geometry(corners, frame.shape)
        area = cv2.contourArea(corners)/(frame.shape[1]*frame.shape[0]) if corners is not None else 0
        ok = detected == must_detect
        verdict = 'OK  ' if ok else 'BAD '
        print(f'{verdict} {label:34s} detected={str(detected):5s} expected={str(must_detect):5s} area={area:.3f}')
        if not ok:
            problems.append(label)
    print(f'\n{len(problems)} wrong of {len(planned)} placements')
    sys.exit(1 if problems else 0)