from dataclasses import dataclass, asdict
from itertools import combinations
import logging
import cv2
import numpy as np
from config import DEFAULT, MarkerConfig
from .preprocessing import preprocess_markers, grayscale
from .perspective import order_points
from .errors import MarkerDetectionError

logger = logging.getLogger(__name__)


@dataclass
class Marker:
    center: tuple[float, float]
    area: float
    side: float
    solidity: float
    extent: float
    blackness: float
    border_distance: float
    polygon: list
    local_contrast: float = 0.0
    solid_ink_fraction: float = 0.0

    def to_dict(self):
        return asdict(self)


def detect_markers(image: np.ndarray, cfg: MarkerConfig = DEFAULT.marker) -> list[Marker]:
    gray = grayscale(image)
    height, width = gray.shape
    candidates = []
    for binary in preprocess_markers(image, cfg):
        # A dark table forms an enclosing foreground contour after inversion.
        # RETR_EXTERNAL then hides every marker on the white sheet inside it.
        # Allow nesting inside large page/background contours, but not inside
        # small printed rings. Filled bubbles nested in those rings may also
        # approximate a quadrilateral and must not become square markers.
        contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        areas = [cv2.contourArea(contour) for contour in contours]
        for index, contour in enumerate(contours):
            parent, depth, small_container = hierarchy[0, index, 3], 0, False
            while parent != -1:
                depth += 1
                if areas[parent] <= cfg.max_area_fraction * width * height:
                    small_container = True
                    break
                parent = hierarchy[0, parent, 3]
            if small_container or depth % 2:
                continue
            area = areas[index]
            if not cfg.min_area_fraction * width * height <= area <= cfg.max_area_fraction * width * height:
                continue
            (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
            if min(rw, rh) < cfg.min_side or not cfg.aspect_min <= rw / rh <= cfg.aspect_max:
                continue
            polygon = cv2.approxPolyDP(contour, cfg.polygon_epsilon * cv2.arcLength(contour, True), True)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                continue
            # A circle can simplify to four vertices at this epsilon. A true
            # square retains most of its area; a diamond inscribed in a filled
            # answer bubble does not, even when its bounding box is square.
            if abs(cv2.contourArea(polygon)) / area < cfg.min_quadrilateral_area_ratio:
                continue
            solidity = area / max(cv2.contourArea(cv2.convexHull(contour)), 1)
            extent = area / (rw * rh)
            if solidity < cfg.min_solidity or extent < cfg.min_extent:
                continue
            moment = cv2.moments(contour)
            cx, cy = moment['m10'] / moment['m00'], moment['m01'] / moment['m00']
            x, y, w, h = cv2.boundingRect(contour)
            local_mask = np.zeros((h, w), np.uint8)
            cv2.drawContours(local_mask, [contour - [x, y]], -1, 255, -1)
            inside = gray[y:y+h, x:x+w][local_mask > 0]
            ink_mean = float(np.mean(inside))
            blackness = 1 - ink_mean / 255
            # Exposure changes absolute gray levels. A marker must instead be
            # a solid square darker than its immediate surroundings. Keep the
            # absolute route for legacy dark markers, with a bounded local route
            # for gray ones; hollow answer boxes must not become markers.
            pad = max(3, round(max(w, h)*0.5))
            x0, y0 = max(0, x-pad), max(0, y-pad)
            x1, y1 = min(width, x+w+pad), min(height, y+h+pad)
            neighborhood = gray[y0:y1, x0:x1]
            surround = np.ones(neighborhood.shape, bool)
            surround[y-y0:y-y0+h, x-x0:x-x0+w] = False
            background = float(np.percentile(neighborhood[surround], 75)) if surround.any() else ink_mean
            contrast = max(0., (background-ink_mean)/max(background, 1.))
            solid = float(np.mean(inside < background-max(cfg.min_local_darkness_delta, (background-ink_mean)*0.5)))
            locally_dark = (contrast >= cfg.min_local_contrast and
                            background-ink_mean >= cfg.min_local_darkness_delta and
                            solid >= cfg.min_solid_ink_fraction)
            if blackness < cfg.min_blackness and not locally_dark:
                continue
            side = float(np.sqrt(area))
            if any(np.linalg.norm(np.asarray(m.center) - (cx, cy)) < cfg.dedup_distance * side for m in candidates):
                continue
            border = min(cx / width, 1 - cx / width, cy / height, 1 - cy / height)
            candidates.append(Marker((cx, cy), area, side, solidity, extent, blackness,
                                     border, polygon.reshape(-1, 2).tolist(), contrast, solid))
    if len(candidates) > cfg.max_candidates:
        raise MarkerDetectionError("Too many square candidates; adjust marker config")
    logger.info("Markers detected: %d", len(candidates))
    return candidates


def _extreme_corner_candidates(markers: list, image_shape, cfg: MarkerConfig) -> np.ndarray | None:
    """Chọn 4 marker gần 4 góc hình ảnh nhất (top-left, top-right, bottom-right, bottom-left).
    Đây là chiến lược chính xác nhất khi 4 marker góc LỚN HƠN các marker nội bộ.
    """
    height, width = image_shape[:2]
    # Tính side trung vị để phát hiện marker nào lớn hơn bình thường
    sides = sorted(m.side for m in markers)
    median_side = sides[len(sides) // 2]

    # Mỗi góc ảnh: tìm marker có score = độ gần góc + bonus nếu lớn hơn trung vị
    corners_of_image = [(0, 0), (width, 0), (width, height), (0, height)]
    selected = []
    used = set()
    for cx, cy in corners_of_image:
        best_m, best_s = None, float('inf')
        for i, m in enumerate(markers):
            if i in used:
                continue
            dist = np.hypot(m.center[0] - cx, m.center[1] - cy)
            # Ưu tiên marker lớn hơn trung vị (là marker góc thật)
            size_bonus = 0.5 if m.side >= median_side * 1.2 else 1.0
            score = dist * size_bonus
            if score < best_s:
                best_m, best_s = (i, m), score
        if best_m is None:
            return None
        used.add(best_m[0])
        selected.append(best_m[1])

    quad = order_points([m.center for m in selected])
    area = abs(cv2.contourArea(quad))
    if area < cfg.min_quad_area_fraction * width * height:
        return None
    if not cv2.isContourConvex(quad.astype(np.float32)):
        return None
    return quad


def select_corner_markers(markers: list[Marker], image_shape,
                          cfg: MarkerConfig = DEFAULT.marker) -> np.ndarray:
    if len(markers) < 4:
        raise MarkerDetectionError("Fewer than four square marker candidates")
    height, width = image_shape[:2]

    # --- Chiến lược 1: ưu tiên 4 marker ở cực ngoài 4 góc ảnh ---
    extreme = _extreme_corner_candidates(markers, image_shape, cfg)
    if extreme is not None:
        logger.info("Corner markers selected via extreme-corner strategy")
        return extreme

    # --- Chiến lược 2 (fallback): brute-force cluster + convex hull ---
    best, best_score = None, -1.0
    visited_clusters = set()
    for seed in markers:
        indices = tuple(i for i, m in enumerate(markers)
                        if 1 / cfg.size_ratio <= m.side / seed.side <= cfg.size_ratio)
        if indices in visited_clusters:
            continue
        visited_clusters.add(indices)
        cluster = [markers[i] for i in indices]
        pts = np.array([m.center for m in cluster], np.float32)
        hull = cv2.convexHull(pts, returnPoints=False).ravel()
        if not 4 <= len(hull) <= cfg.max_hull_points:
            continue
        for indices in combinations(hull, 4):
            selected = [cluster[i] for i in indices]
            if max(m.side for m in selected) / min(m.side for m in selected) > cfg.size_ratio:
                continue
            quad = order_points([m.center for m in selected])
            area = abs(cv2.contourArea(quad))
            if area < cfg.min_quad_area_fraction * width * height:
                continue
            proximity = np.mean([max(0, 1 - m.border_distance / cfg.border_band) for m in selected])
            consistency = min(m.side for m in selected) / max(m.side for m in selected)
            score = area * consistency * (1 + proximity)
            if score > best_score:
                best, best_score = quad, score
    if best is None:
        raise MarkerDetectionError("No consistent outer marker quadrilateral")
    logger.info("Corner markers selected via brute-force strategy")
    return best
