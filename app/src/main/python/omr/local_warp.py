"""Bounded piecewise affine rectification using marker landmarks, never answers."""
import cv2
import numpy as np
from config import DEFAULT
from .errors import AlignmentError


def build_marker_mesh(expected, observed, size, cfg=DEFAULT.geometry):
    expected, observed = np.asarray(expected, float), np.asarray(observed, float)
    if len(expected) < cfg.local_warp_min_markers:
        raise AlignmentError('Insufficient landmarks for local rectification')
    if np.max(np.linalg.norm(expected-observed, axis=1)) > cfg.local_warp_max_displacement:
        raise AlignmentError('Local displacement exceeds configured limit')
    width, height = size
    boundary = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], float)
    target = np.vstack([boundary, expected])
    source = np.vstack([boundary, observed])
    if np.any(target < 0) or np.any(target >= size):
        raise AlignmentError('Local landmarks outside image')
    triangulation = cv2.Subdiv2D((0, 0, width, height))
    for point in target:
        triangulation.insert(tuple(map(float, point)))
    triangles = []
    for triangle in triangulation.getTriangleList().reshape(-1, 3, 2):
        ids = [int(np.argmin(np.linalg.norm(target-p, axis=1))) for p in triangle]
        if len(set(ids)) != 3 or np.max(np.linalg.norm(target[ids]-triangle, axis=1)) > 1:
            continue
        dest, src = target[ids].astype(np.float32), source[ids].astype(np.float32)
        if abs(cv2.contourArea(dest)) < cfg.local_warp_min_triangle_area:
            raise AlignmentError('Degenerate local marker triangle')
        affine = cv2.getAffineTransform(dest, src)
        scales = np.linalg.svd(affine[:, :2], compute_uv=False)
        if np.linalg.det(affine[:, :2]) <= 0 or min(scales) < cfg.local_warp_min_scale or max(scales) > cfg.local_warp_max_scale:
            raise AlignmentError('Local marker mapping folds or stretches excessively')
        triangles.append(ids)
    if not triangles:
        raise AlignmentError('No local marker triangles')
    return {'source_points': source.tolist(), 'target_points': target.tolist(), 'triangles': triangles,
            'coordinate_system': 'pre_refinement_canonical_pixels_to_canonical_pixels'}


def map_mesh_points(points, mesh, inverse=False):
    """Map pre-refinement -> final canonical; inverse maps final -> pre-refinement."""
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    source = np.asarray(mesh['target_points' if inverse else 'source_points'], float)
    target = np.asarray(mesh['source_points' if inverse else 'target_points'], float)
    output, assigned = points.copy(), np.zeros(len(points), bool)
    for ids in mesh['triangles']:
        src, dst = source[ids], target[ids]
        basis = np.column_stack([src[1]-src[0], src[2]-src[0]])
        uv = (points-src[0])@np.linalg.inv(basis).T
        inside = (uv[:, 0] >= -1e-6) & (uv[:, 1] >= -1e-6) & (uv.sum(axis=1) <= 1+1e-6) & ~assigned
        output[inside] = dst[0]+uv[inside]@np.stack([dst[1]-dst[0], dst[2]-dst[0]])
        assigned |= inside
    if not assigned.all():
        raise AlignmentError('Point outside local rectification mesh')
    return output


def warp_with_mesh(original, homography, size, mesh):
    width, height = size
    map_y, map_x = np.indices((height, width), dtype=np.float32)
    target, source = np.asarray(mesh['target_points'], np.float32), np.asarray(mesh['source_points'], np.float32)
    for ids in mesh['triangles']:
        dst, src = target[ids], source[ids]
        x, y, w, h = cv2.boundingRect(dst)
        w, h = min(w, width-x), min(h, height-y)
        yy, xx = np.indices((h, w), dtype=np.float32)
        xx, yy = xx+x, yy+y
        affine = cv2.getAffineTransform(dst, src)
        mask = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(mask, np.round(dst-[x, y]).astype(np.int32), 1)
        inside = mask > 0
        map_x[y:y+h, x:x+w][inside] = (affine[0, 0]*xx+affine[0, 1]*yy+affine[0, 2])[inside]
        map_y[y:y+h, x:x+w][inside] = (affine[1, 0]*xx+affine[1, 1]*yy+affine[1, 2])[inside]
    # Compose inverse homography before sampling to avoid two image resamplings.
    inverse = np.linalg.inv(homography)
    denominator = inverse[2, 0]*map_x+inverse[2, 1]*map_y+inverse[2, 2]
    original_x = (inverse[0, 0]*map_x+inverse[0, 1]*map_y+inverse[0, 2])/denominator
    original_y = (inverse[1, 0]*map_x+inverse[1, 1]*map_y+inverse[1, 2])/denominator
    return cv2.remap(original, original_x.astype(np.float32), original_y.astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
