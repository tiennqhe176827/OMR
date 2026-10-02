import cv2
import numpy as np
from .models import GridDefinition
from .errors import PerspectiveError


def transform_points(points, homography: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    projected = np.column_stack([pts, np.ones(len(pts))]) @ homography.T
    if np.any(np.abs(projected[:, 2]) < np.finfo(float).eps):
        raise PerspectiveError("Point projects to infinity")
    return projected[:, :2] / projected[:, 2:]


def original_to_canonical(points, homography, mesh=None):
    projected = transform_points(points, homography)
    if mesh is not None:
        from .local_warp import map_mesh_points
        projected = map_mesh_points(projected, mesh)
    return projected


def canonical_to_original(points, homography, mesh=None):
    if mesh is not None:
        from .local_warp import map_mesh_points
        points = map_mesh_points(points, mesh, inverse=True)
    return transform_points(points, np.linalg.inv(homography))


def canonical_to_roi(points, roi_origin):
    return np.asarray(points, dtype=float) - np.asarray(roi_origin)


def roi_to_canonical(points, roi_origin):
    return np.asarray(points, dtype=float) + np.asarray(roi_origin)


def roi_to_block(points, block_origin):
    return canonical_to_roi(points, block_origin)


def block_to_roi(points, block_origin):
    return roi_to_canonical(points, block_origin)


def normalized_to_pixel(point, size):
    return np.asarray(point, dtype=float) * np.asarray(size)


def pixel_to_normalized(point, size):
    return np.asarray(point, dtype=float) / np.asarray(size)


def radius_to_pixel(radius: float, size: tuple[int, int]) -> float:
    return radius * min(size)


def generate_grid(grid: GridDefinition) -> np.ndarray:
    if min(grid.rows, grid.columns) < 1 or grid.radius <= 0:
        raise ValueError("Grid dimensions and radius must be positive")
    return np.array([[np.asarray(grid.origin) + c * np.asarray(grid.column_step)
                      + r * np.asarray(grid.row_step) for c in range(grid.columns)]
                     for r in range(grid.rows)])
