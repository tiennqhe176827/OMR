import cv2
import numpy as np
from config import DEFAULT
from .errors import PerspectiveError


def order_points(points) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    if len(np.unique(pts, axis=0)) != 4:
        raise PerspectiveError("Four distinct corners required")
    center = pts.mean(axis=0)
    ordered = pts[np.argsort(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]))]
    ordered = np.roll(ordered, -int(np.argmin(ordered.sum(axis=1))), axis=0)
    if not cv2.isContourConvex(ordered.reshape(-1, 1, 2)):
        raise PerspectiveError("Corners must form a convex quadrilateral")
    return ordered


def homography_from_corners(source, destination) -> np.ndarray:
    src = np.asarray(source, np.float32).reshape(4, 2)
    dst = np.asarray(destination, np.float32).reshape(4, 2)
    if min(abs(cv2.contourArea(src)), abs(cv2.contourArea(dst))) < DEFAULT.geometry.min_polygon_area:
        raise PerspectiveError("Degenerate quadrilateral")
    matrix = cv2.getPerspectiveTransform(src, dst)
    if not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < DEFAULT.geometry.min_homography_determinant:
        raise PerspectiveError("Invalid homography")
    return matrix


def warp_sheet(image, homography, size):
    return cv2.warpPerspective(image, homography, tuple(map(int, size)),
                               flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
