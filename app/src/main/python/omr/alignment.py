import logging
import cv2
import numpy as np
from config import DEFAULT, GeometryConfig
from .marker_detection import detect_markers
from .orientation import edge_error, stable_mask
from .perspective import warp_sheet
from .errors import AlignmentError
from .preprocessing import grayscale
from .roi_extraction import REGION_NAMES, crop
from .local_warp import build_marker_mesh, warp_with_mesh

logger = logging.getLogger(__name__)


def bounded_affine_correction(pairs, expected, size, cfg):
    """Fit small scale/rotation/shear errors; reject weak or extrapolated fits."""
    if len(pairs) < cfg.affine_min_markers:
        return None
    source = np.asarray([p[2] for p in pairs], dtype=np.float64)
    destination = np.asarray([expected[p[0]] for p in pairs], dtype=np.float64)
    if np.any(np.ptp(source, axis=0)/size < cfg.affine_min_coverage):
        return None
    affine, inliers = cv2.estimateAffine2D(source, destination, method=cv2.RANSAC,
        ransacReprojThreshold=cfg.affine_ransac_error, maxIters=cfg.affine_max_iterations,
        confidence=cfg.affine_confidence, refineIters=cfg.affine_refine_iterations)
    if affine is None or inliers is None or not np.isfinite(affine).all():
        return None
    keep = inliers.ravel().astype(bool)
    if keep.sum() < cfg.affine_min_markers or keep.mean() < cfg.affine_min_inlier_fraction:
        return None
    if np.any(np.ptp(source[keep], axis=0)/size < cfg.affine_min_coverage):
        return None
    if np.linalg.det(affine[:, :2]) <= 0 or np.linalg.norm(affine[:, :2]-np.eye(2), ord=2) > cfg.affine_max_linear_change:
        return None
    probes = np.array([[0, 0], [size[0], 0], size, [0, size[1]]], dtype=float)
    displacements = probes@affine[:, :2].T+affine[:, 2]-probes
    if np.max(np.linalg.norm(displacements, axis=1)) > cfg.alignment_refine_limit:
        return None
    correction = np.eye(3)
    correction[:2] = affine
    return correction


def check_local_anchors(warped, reference, template, cfg):
    """Check printed ring/frame anchors per block to reject local bending/drift."""
    # Scanner whitening can suppress faint printed rings below fixed Canny
    # thresholds. Normalize local contrast on BOTH images before comparing edges.
    # This affects geometry validation only, never the pixels used to score ink.
    clahe = cv2.createCLAHE(clipLimit=cfg.anchor_clahe_clip,
                          tileGridSize=(cfg.anchor_clahe_tiles, cfg.anchor_clahe_tiles))
    ref_edges = cv2.Canny(clahe.apply(grayscale(reference)), cfg.edge_threshold, cfg.edge_threshold*2)
    test_edges = cv2.Canny(clahe.apply(grayscale(warped)), cfg.edge_threshold, cfg.edge_threshold*2)
    mask = stable_mask(template, reference.shape)
    ref_edges[mask == 0] = 0
    distances = cv2.distanceTransform(255-test_edges, cv2.DIST_L2, 3)
    errors, drifting = {}, []
    for name in REGION_NAMES:
        roi_edges, _ = crop(ref_edges, template['regions'][name])
        roi_dist, _ = crop(distances, template['regions'][name])
        for block in template[name]['blocks']:
            edges, _ = crop(roi_edges, block['rect'])
            dist, _ = crop(roi_dist, block['rect'])
            key = f"{name}/{block['id']}"
            if np.count_nonzero(edges) < cfg.local_alignment_min_edges:
                raise AlignmentError(f"Insufficient independent printed anchors: {key}")
            error = float(np.mean(np.minimum(dist[edges > 0], cfg.edge_distance_cap)))
            errors[key] = error
            if error > cfg.local_alignment_max_error:
                drifting.append((key, error))
    # Report every drifting block, not only the first. Aborting early hid the
    # real shape of the drift from camera diagnostics, which made field reports
    # point at one block while most of the sheet was moving.
    if drifting:
        worst = sorted(drifting, key=lambda item: -item[1])
        summary = ", ".join(f"{key}={error:.2f}px" for key, error in worst[:3])
        raise AlignmentError(f"Local block alignment failed in {len(drifting)} block(s) "
                             f"over {cfg.local_alignment_max_error:.1f}px: {summary}")
    return errors


def match_auxiliary(image, expected, cfg):
    detected = detect_markers(image)
    observed = np.array([m.center for m in detected], dtype=float).reshape(-1, 2)
    pairs, used = [], set()
    if not len(observed):
        return pairs
    # One-to-one nearest matching, limited to a small calibrated neighborhood.
    distances = np.linalg.norm(expected[:, None, :]-observed[None, :, :], axis=2)
    for flat in np.argsort(distances, axis=None):
        i, j = np.unravel_index(flat, distances.shape)
        if distances[i, j] > cfg.marker_match_radius:
            break
        if i not in {p[0] for p in pairs} and j not in used:
            pairs.append((int(i), expected[i]-observed[j], observed[j]))
            used.add(j)
    return pairs


def validate_alignment(warped, matrix, original, template, reference,
                       cfg: GeometryConfig = DEFAULT.geometry):
    size = (template['canonical_size']['width'], template['canonical_size']['height'])
    expected = np.array(template['markers']['auxiliary'])*size
    required = max(cfg.min_aux_markers, int(np.ceil(len(expected)*cfg.required_aux_fraction)))
    pairs = match_auxiliary(warped, expected, cfg)
    error_before = max((float(np.linalg.norm(p[1])) for p in pairs), default=None)
    methods = []
    refinement_rejections = []
    local_mesh = None

    def diagnostics(status, error, edges=None):
        return {'status': status, 'error_px': error, 'error_before_px': error_before,
                'threshold_px': cfg.alignment_max_error, 'edge_error_preview_px': edges,
                'auxiliary_matched': len(pairs), 'auxiliary_expected': len(expected),
                'auxiliary_required': required, 'refined': bool(methods), 'refinement_methods': list(methods),
                'refinement_rejections': list(refinement_rejections),
                'local_anchor_preprocessing': 'clahe',
                'anchors': [{'index': p[0], 'expected': expected[p[0]].tolist(), 'observed': p[2].tolist(),
                             'error_px': float(np.linalg.norm(p[1]))} for p in pairs]}

    if len(pairs) < required:
        raise AlignmentError(f"Only {len(pairs)}/{required} independent auxiliary markers matched",
                             diagnostics('failed', error_before), warped)
    residuals = np.array([p[1] for p in pairs])
    error = float(np.max(np.linalg.norm(residuals, axis=1)))
    refined = False
    if cfg.alignment_max_error < error <= cfg.alignment_refine_limit:
        shift = np.median(residuals, axis=0)
        correction = np.eye(3)
        correction[:2, 2] = shift
        proposed_matrix = correction @ matrix
        proposed = warp_sheet(original, proposed_matrix, size)
        new_pairs = match_auxiliary(proposed, expected, cfg)
        if len(new_pairs) >= required and {p[0] for p in pairs} <= {p[0] for p in new_pairs}:
            new_error = max(float(np.linalg.norm(p[1])) for p in new_pairs)
            if new_error < error:
                warped, matrix, pairs, error = proposed, proposed_matrix, new_pairs, new_error
                refined = True
                methods.append('translation')
    if cfg.alignment_max_error < error <= cfg.alignment_refine_limit:
        correction = bounded_affine_correction(pairs, expected, size, cfg)
        if correction is not None:
            proposed_matrix = correction @ matrix
            proposed = warp_sheet(original, proposed_matrix, size)
            new_pairs = match_auxiliary(proposed, expected, cfg)
            if len(new_pairs) >= required and {p[0] for p in pairs} <= {p[0] for p in new_pairs}:
                new_error = max(float(np.linalg.norm(p[1])) for p in new_pairs)
                # Validate ALL matched markers, including RANSAC outliers.
                if new_error < error:
                    warped, matrix, pairs, error = proposed, proposed_matrix, new_pairs, new_error
                    refined = True
                    methods.append('affine_ransac')
    edges = edge_error(reference, warped, stable_mask(template, reference.shape), cfg)
    local_anchors_failed = False
    if error <= cfg.alignment_max_error and edges <= cfg.alignment_edge_max:
        try:
            check_local_anchors(warped, reference, template, cfg)
        except AlignmentError:
            local_anchors_failed = True
    # Dense independent form markers can describe curvature that one homography
    # cannot. Accept only after testing printed edges NOT used to construct mesh.
    if ((error > cfg.alignment_max_error or local_anchors_failed)
            and error <= cfg.local_warp_max_displacement
            and len(pairs) >= cfg.local_warp_min_markers and edges <= cfg.alignment_edge_max):
        all_expected = np.vstack([expected, np.asarray(template['markers']['corners'])*size])
        all_pairs = match_auxiliary(warped, all_expected, cfg)
        if len(all_pairs) >= len(pairs)+4:
            try:
                proposal = build_marker_mesh([all_expected[p[0]] for p in all_pairs], [p[2] for p in all_pairs], size, cfg)
                proposed = warp_with_mesh(original, matrix, size, proposal)
                new_pairs = match_auxiliary(proposed, expected, cfg)
                if len(new_pairs) >= required and {p[0] for p in pairs} <= {p[0] for p in new_pairs}:
                    new_error = max(float(np.linalg.norm(p[1])) for p in new_pairs)
                    new_edges = edge_error(reference, proposed, stable_mask(template, reference.shape), cfg)
                    check_local_anchors(proposed, reference, template, cfg)
                    if new_error <= cfg.alignment_max_error and new_edges <= cfg.alignment_edge_max and new_edges < edges:
                        warped, pairs, error, edges = proposed, new_pairs, new_error, new_edges
                        local_mesh, refined = proposal, True
                        methods.append('piecewise_affine_markers')
            except AlignmentError as exc:
                refinement_rejections.append({'method': 'piecewise_affine_markers', 'reason': str(exc)})
                logger.info('Local rectification rejected: %s', exc)
    details = diagnostics('failed', error, edges)
    if error > cfg.alignment_max_error or edges > cfg.alignment_edge_max:
        raise AlignmentError(f"Marker error={error:.2f}px, printed-anchor error={edges:.2f} preview px", details, warped)
    try:
        local_errors = check_local_anchors(warped, reference, template, cfg)
    except AlignmentError as exc:
        details['local_failure'] = str(exc)
        raise AlignmentError(str(exc), details, warped) from exc
    logger.info("Alignment error = %.3f px", error)
    return warped, matrix, {**details, 'status': 'ok', 'error_px': error, 'edge_error_preview_px': edges,
                            'auxiliary_matched': len(pairs), 'auxiliary_expected': len(expected),
                            'refined': refined, 'confidence': float(np.exp(-error/cfg.alignment_max_error)),
                            'local_block_errors_px': local_errors,
                            'local_mesh': local_mesh,
                            'anchors': [{'expected': expected[p[0]].tolist(), 'observed': p[2].tolist()} for p in pairs]}
