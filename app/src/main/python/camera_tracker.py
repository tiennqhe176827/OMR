"""Single-frame A4 localization for retaining the actual camera pixels.

The adapter waits for two seconds of stable corners before capture. The full-resolution
frame goes through OMR before any result is accepted or graded.
"""
from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np

from omr.errors import OMRError
from omr.marker_detection import detect_markers, select_corner_markers
from omr.perspective import order_points


@dataclass(frozen=True)
class Observation:
    centers: np.ndarray
    features: np.ndarray
    side: float
    candidate_count: int


class SheetTracker:
    DETECT_WIDTH = 768
    A4_ASPECT = 210 / 297
    MIN_PAPER_FILL = .70
    MARKER_AREA_WITHIN_PAPER = .85 * (0.9508928571428571 - 0.049107142857142856)

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = 'searching'
        self.corners = None
        self.side = None
        self.stable_frames = 0
        self.frame_size = None
        self.last_metrics = {}

    @staticmethod
    def _guide_targets(shape):
        h, w = shape
        # Match the four outer marker centers on the current printed template.
        aspect = w / h
        # Let the marker quadrilateral occupy most of the camera view. A small
        # centered sheet can still have four detectable squares, but its answer
        # bubbles lose too many pixels for reliable grading.
        guide_width = min(.96, .96 * SheetTracker.A4_ASPECT / aspect)
        guide_height = guide_width * aspect / SheetTracker.A4_ASPECT
        x0, x1 = (1-guide_width)/2, (1+guide_width)/2
        y0, y1 = (1-guide_height)/2, (1+guide_height)/2
        # Guide surrounds paper edges; marker targets are inset on the printed A4.
        x0, x1 = x0 + .075 * guide_width, x1 - .075 * guide_width
        y0, y1 = y0 + .049107 * guide_height, y1 - .049107 * guide_height
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float32)

    @classmethod
    def _corner_hits(cls, markers, shape):
        if not markers:
            return [None] * 4
        h, w = shape
        targets = cls._guide_targets(shape)
        min_side = max(4., np.percentile([m.side for m in markers], 65) * .75)
        eligible = [m for m in markers if m.side >= min_side]
        hits = []
        for target in targets:
            if not eligible:
                hits.append(None)
                continue
            nearest = min(eligible, key=lambda m: np.linalg.norm(np.asarray(m.center)/[w, h]-target))
            point = np.asarray(nearest.center)/[w, h]
            hits.append(point.tolist() if np.linalg.norm(point-target) <= .18 else None)
        return hits

    @staticmethod
    def _geometry(corners, shape):
        h, w = shape
        q = np.asarray(corners, np.float32).reshape(4, 2)
        if not np.isfinite(q).all() or np.any(q[:, 0] < 0) or np.any(q[:, 1] < 0):
            return False
        if np.any(q[:, 0] >= w) or np.any(q[:, 1] >= h) or not cv2.isContourConvex(q):
            return False
        if cv2.contourArea(q) < .17 * w * h:
            return False
        sides = np.linalg.norm(q - np.roll(q, -1, axis=0), axis=1)
        if min(sides) < 8 or max(sides) / min(sides) > 3.5:
            return False
        # Plain corner squares have no ID. A missing outer square can be
        # replaced by a large inner registration square, producing one side
        # of the sheet much shorter than its opposite side.
        if min(sides[0], sides[2]) / max(sides[0], sides[2]) < .73:
            return False
        if min(sides[1], sides[3]) / max(sides[1], sides[3]) < .73:
            return False
        return True

    @staticmethod
    def _paper_outline(gray):
        """Find a complete, printed sheet for immediate still capture.

        The JPEG pipeline, not this preview heuristic, decides whether its
        markers and answers are valid. Require a large, enclosed bright quad
        so a tiny marker or a clipped sheet cannot fire the shutter.
        """
        h, w = gray.shape
        softened = cv2.GaussianBlur(gray, (5, 5), 0)
        for method in (cv2.THRESH_OTSU, cv2.THRESH_TRIANGLE):
            _, binary = cv2.threshold(softened, 0, 255, cv2.THRESH_BINARY | method)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
                area = cv2.contourArea(contour)
                if area < .20 * w * h or area > .97 * w * h:
                    continue
                polygon = cv2.approxPolyDP(contour, .025 * cv2.arcLength(contour, True), True)
                if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                    continue
                points = order_points(polygon.reshape(4, 2).astype(np.float32))
                margin = .01 * min(w, h)
                if (np.min(points[:, 0]) < margin or np.max(points[:, 0]) > w - margin or
                        np.min(points[:, 1]) < margin or np.max(points[:, 1]) > h - margin):
                    continue
                sides = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
                aspect = (sides[0] + sides[2]) / max(sides[1] + sides[3], 1)
                if not .48 <= aspect <= 1.02:
                    continue
                mask = np.zeros((h, w), np.uint8)
                cv2.fillConvexPoly(mask, points.astype(np.int32), 255)
                inside = gray[cv2.erode(mask, np.ones((9, 9), np.uint8)) > 0]
                outside = gray[mask == 0]
                if not len(inside) or not len(outside) or np.median(inside) < np.median(outside) + 8:
                    continue
                if np.count_nonzero(inside < np.median(inside) - 35) < .003 * len(inside):
                    continue
                return points
        return None

    def _detect(self, gray, markers=None):
        if markers is None:
            markers = detect_markers(gray)
        corners = select_corner_markers(markers, gray.shape)
        if not self._geometry(corners, gray.shape):
            raise ValueError('Invalid outer marker geometry')
        selected = []
        used = set()
        for center in corners:
            ranked = sorted(range(len(markers)), key=lambda i: np.linalg.norm(np.asarray(markers[i].center)-center))
            index = next(i for i in ranked if i not in used)
            used.add(index)
            selected.append(markers[index])
        features = np.array([m.polygon for m in selected], np.float32).reshape(16, 2)
        return Observation(np.asarray(corners, np.float32), features,
                           float(np.median([m.side for m in selected])), len(markers))

    def observe(self, frame, capture_timestamp_ns=None):
        """One-frame localization. Never wait for previous positions or sharpness."""
        started = perf_counter()
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        scale = min(1., self.DETECT_WIDTH / width)
        small = (cv2.resize(gray, (round(width*scale), round(height*scale)), interpolation=cv2.INTER_AREA)
                 if scale < 1 else gray)
        h, w = small.shape
        self.frame_size = small.shape
        paper = self._paper_outline(small)
        paper_fill = 0. if paper is None else float(cv2.contourArea(paper)) / small.size
        candidates = []
        observation = None
        detect_ms = 0.
        # Complete close paper: retain immediately. Marker detection is deferred to OMR.
        if paper_fill < self.MIN_PAPER_FILL:
            began = perf_counter()
            try:
                candidates = detect_markers(small)
                observation = self._detect(small, candidates)
            except (OMRError, ValueError):
                pass
            detect_ms = (perf_counter() - began) * 1000
        self.corners = None if observation is None else observation.centers
        self.side = None if observation is None else observation.side
        self.state = 'locked' if observation is not None else 'page_detected' if paper is not None else 'searching'
        self.stable_frames = 1 if self.state != 'searching' else 0
        corner_hits = self._corner_hits(candidates, small.shape)
        marker_area = 0.
        if observation is not None:
            corner_hits = (observation.centers / [w, h]).tolist()
            marker_area = float(cv2.contourArea(observation.centers)) / small.size
            if paper is None:
                paper_fill = min(1., marker_area / self.MARKER_AREA_WITHIN_PAPER)
        found = observation is not None or paper is not None
        too_small = found and paper_fill < self.MIN_PAPER_FILL
        capture_ready = found and not too_small
        capture_source = 'paper' if paper is not None else 'markers' if observation is not None else None
        message = ('Đã nhận phiếu A4.' if capture_ready else
                   'Đưa máy gần hơn — để mép giấy A4 gần sát khung xanh.' if too_small else
                   'Đưa trọn giấy A4 vào khung xanh; chạm phiếu để lấy nét nếu cần.')
        metrics = {'state': self.state, 'total_ms': round((perf_counter()-started)*1000, 2),
                   'detect_ms': round(detect_ms, 2), 'source': capture_source,
                   'paper_area_fraction': round(paper_fill, 3),
                   'sheet_area_fraction': round(marker_area, 3),
                   'marker_side_at_960px': round((self.side or 0) * 960 / w, 1),
                   'candidate_count': len(candidates), 'stable_frames': self.stable_frames,
                   'capture_source': capture_source,
                   'capture_blocker': None if capture_ready else 'move_closer' if too_small else 'paper_not_found'}
        self.last_metrics = metrics
        quad = paper if paper is not None else self.corners
        return {'state': self.state, 'message': message,
                'corners': None if quad is None else (quad / [w, h]).tolist(),
                'corner_hits': corner_hits, 'corner_count': sum(hit is not None for hit in corner_hits),
                'too_small': too_small, 'capture_ready': capture_ready, 'metrics': metrics}
