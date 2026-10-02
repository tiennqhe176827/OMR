import cv2
import numpy as np
from config import DEFAULT, GeometryConfig
from .perspective import homography_from_corners, warp_sheet
from .preprocessing import grayscale
from .roi_extraction import iter_groups
from .errors import OrientationError


def stable_mask(template: dict, shape) -> np.ndarray:
    height, width = shape[:2]
    mask = np.full((height, width), 255, np.uint8)
    for _, _, group in iter_groups(template):
        for b in group['bubbles']:
            center = (round(b['cx']*width), round(b['cy']*height))
            radius = round(b['radius']*min(width, height)*DEFAULT.geometry.stable_interior_ratio)
            cv2.circle(mask, center, radius, 0, -1)
    return mask


def edge_error(reference, test, mask=None, cfg: GeometryConfig = DEFAULT.geometry) -> float:
    size = (cfg.orientation_width, round(reference.shape[0]*cfg.orientation_width/reference.shape[1]))
    ref = cv2.resize(grayscale(reference), size, interpolation=cv2.INTER_AREA)
    cur = cv2.resize(grayscale(test), size, interpolation=cv2.INTER_AREA)
    clahe = cv2.createCLAHE(clipLimit=cfg.anchor_clahe_clip,
                            tileGridSize=(cfg.anchor_clahe_tiles, cfg.anchor_clahe_tiles))
    ref = clahe.apply(ref)
    cur = clahe.apply(cur)
    ref_edge = cv2.Canny(ref, cfg.edge_threshold, cfg.edge_threshold*2) > 0
    test_edge = cv2.Canny(cur, cfg.edge_threshold, cfg.edge_threshold*2)
    if mask is not None:
        ref_edge &= cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST) > 0
    if int(ref_edge.sum()) < cfg.min_reference_edges:
        raise OrientationError("Insufficient stable printed anchors in reference")
    distance = cv2.distanceTransform(255-test_edge, cv2.DIST_L2, 3)
    return float(np.minimum(distance[ref_edge], cfg.edge_distance_cap).mean())



def resolve_orientation(image, corners, template, reference, cfg: GeometryConfig = DEFAULT.geometry):
    size = (template['canonical_size']['width'], template['canonical_size']['height'])
    destination = np.asarray(template['markers']['corners'], np.float32)*size
    mask = stable_mask(template, reference.shape)
    trials = []
    for turns in range(4):
        matrix = homography_from_corners(np.roll(corners, -turns, axis=0), destination)
        warped = warp_sheet(image, matrix, size)
        trials.append((edge_error(reference, warped, mask, cfg), turns, matrix, warped))
    trials.sort(key=lambda trial: trial[0])
    best, second = trials[:2]
    if best[0] > cfg.orientation_max_error or second[0]-best[0] < cfg.orientation_min_margin:
        raise OrientationError(f"Orientation uncertain: errors={[round(t[0], 3) for t in trials]}")
    return best[3], best[2], {'status': 'ok', 'corner_shift_degrees': best[1]*90,
                              'edge_error': best[0], 'runner_up_error': second[0],
                              'confidence': float(np.clip((second[0]-best[0])/max(second[0], 1e-6), 0, 1))}
