import logging
from time import perf_counter
import numpy as np
from config import DEFAULT
from .errors import OMRError, TemplateError, AlignmentError
from .io import read_image
from .template_loader import load_template
from .quality import assess_quality, validate_quality
from .marker_detection import detect_markers, select_corner_markers
from .orientation import resolve_orientation
from .alignment import validate_alignment
from .roi_extraction import extract_main_regions, crop, pixel_rect, REGION_NAMES
from .preprocessing import preprocess_omr_roi
from .models import Bubble
from .illumination import normalize_illumination
from .bubble_scoring import score_bubble
from .thresholding import estimate_fill_threshold, classify_group
from .decoder import decode_sections
from .visualization import draw_markers, draw_alignment, draw_template, draw_result, draw_grid
from .grid_registration import register_grids

logger = logging.getLogger(__name__)


def process_exam_sheet(image_path: str | np.ndarray, template_path: str, debug: bool = False, corners: np.ndarray = None):
    """Return (JSON-serializable result, dict[str, ndarray] debug images).

    Expected input/geometry failures become structured errors; no answers are
    emitted until alignment passes. Unexpected programming errors propagate.
    """
    started = perf_counter()
    artifacts, quality = {}, {}
    result = {'status': 'error', 'quality': quality}
    try:
        # Camera callers pass an in-memory BGR frame; desktop paths stay supported.
        image = image_path if isinstance(image_path, np.ndarray) else read_image(image_path)
        if debug:
            artifacts['01_original'] = image.copy()
        quality.update(assess_quality(image))
        validate_quality(quality)
        loaded = load_template(template_path)
        template = loaded.data
        experimental = template['calibration_status'] == 'experimental'
        if experimental:
            result['warnings'] = [template['calibration_notes']]
        result['template'] = {'id': template['template_id'], 'version': template['template_version'],
                              'calibration_status': template['calibration_status']}
        reference = read_image(loaded.reference_path)
        width, height = template['canonical_size']['width'], template['canonical_size']['height']
        if reference.shape[:2] != (height, width):
            raise TemplateError("Reference dimensions differ from canonical_size")
        if corners is None:
            markers = detect_markers(image)
            if debug:
                artifacts['02_marker_candidates'] = draw_markers(image, markers)
            corners = select_corner_markers(markers, image.shape)
            quality['marker_detection'] = {'status': 'ok', 'candidate_count': len(markers),
                                           'confidence': float(np.mean([m.blackness for m in markers]))}
            if debug:
                artifacts['03_markers_selected'] = draw_markers(image, markers, corners)
        else:
            quality['marker_detection'] = {'status': 'ok', 'candidate_count': 4, 'confidence': 1.0}
            if debug:
                artifacts['03_markers_selected'] = draw_markers(image, [], corners)
        warped, matrix, orientation = resolve_orientation(image, corners, template, reference)
        warped = normalize_illumination(warped)
        quality['orientation'] = orientation
        quality['perspective'] = {'status': 'ok'}
        if debug:
            artifacts['04_warped'] = warped.copy()
        warped, matrix, alignment = validate_alignment(warped, matrix, image, template, reference)
        quality['alignment'] = alignment
        result['alignment'] = {'original_to_canonical': matrix.tolist(),
                               'canonical_to_original': np.linalg.inv(matrix).tolist(),
                               'canonical_size': template['canonical_size'], **alignment}
        if alignment.get('local_mesh') is not None:
            result['alignment'].update(coordinate_model='homography_then_piecewise_affine',
                original_to_canonical=None, canonical_to_original=None,
                original_to_pre_refinement=matrix.tolist(), pre_refinement_to_original=np.linalg.inv(matrix).tolist())
        else:
            result['alignment']['coordinate_model'] = 'homography'
        scoring_template = template
        if alignment.get('local_mesh') is not None:
            try:
                scoring_template, grid_report = register_grids(warped, reference, template)
            except AlignmentError as exc:
                details = {**alignment, 'status': 'failed', 'grid_failure': str(exc)}
                raise AlignmentError(str(exc), details, warped) from exc
            result['alignment']['grid_registration'] = grid_report
        if debug:
            artifacts['04_warped'] = warped.copy()
            artifacts['05_alignment'] = draw_alignment(warped, alignment)
        rois = extract_main_regions(warped, scoring_template)
        reference_rois = extract_main_regions(reference, template)
        measurements, thresholds, decisions = {}, {}, {}
        for index, name in enumerate(REGION_NAMES, 6):
            roi = rois[name]
            if debug:
                artifacts[f'{index:02d}_roi_{name}'] = roi
            r = pixel_rect(scoring_template['regions'][name], (width, height))
            ref_r = pixel_rect(template['regions'][name], (width, height))
            region_scores, region_ids = [], []
            for block in scoring_template[name]['blocks']:
                block_image, brect = crop(roi, block['rect'])
                gray, binary = preprocess_omr_roi(block_image)
                ref_definition = next(item for item in template[name]['blocks'] if item['id'] == block['id'])
                ref_block, ref_brect = crop(reference_rois[name], ref_definition['rect'])
                ref_gray, ref_binary = preprocess_omr_roi(ref_block)
                reference_bubbles = {(g['id'], b['symbol']): b for g in ref_definition['groups'] for b in g['bubbles']}
                if debug:
                    artifacts[f"crops/{name}_{block['id']}"] = block_image
                    artifacts[f"crops/{name}_{block['id']}_binary"] = binary
                for group in block['groups']:
                    region_ids.append(group['id'])
                    scores = {}
                    for b in group['bubbles']:
                        bubble = Bubble(f"{group['id']}:{b['symbol']}", b['symbol'],
                                        b['cx']*width-r.x-brect.x, b['cy']*height-r.y-brect.y,
                                        b['radius']*min(width, height))
                        scores[b['symbol']] = score_bubble(gray, binary, bubble)
                        scores[b['symbol']].update(center_canonical=[bubble.cx+r.x+brect.x, bubble.cy+r.y+brect.y],
                                                   radius_px=bubble.radius)
                        ref_b = reference_bubbles[(group['id'], b['symbol'])]
                        ref_bubble = Bubble(bubble.id, b['symbol'], ref_b['cx']*width-ref_r.x-ref_brect.x,
                                            ref_b['cy']*height-ref_r.y-ref_brect.y, ref_b['radius']*min(width, height))
                        baseline = (score_bubble(ref_gray, ref_binary, ref_bubble)['score']
                                    if template.get('baseline_policy', 'blank_reference') == 'blank_reference' else 0.0)
                        raw = scores[b['symbol']]['score']
                        scores[b['symbol']].update(raw_score=raw, reference_score=baseline,
                                                   score=float(np.clip((raw-baseline)/max(1-baseline, DEFAULT.decision.epsilon), 0, 1)))
                        region_scores.append(scores[b['symbol']]['score'])
                    measurements[group['id']] = scores
            thresholds[name] = estimate_fill_threshold(region_scores)
            logger.info("%s threshold = %.3f (%s)", name, thresholds[name]['min_fill'], thresholds[name]['method'])
            for group_id in region_ids:
                scores = {symbol: value['score'] for symbol, value in measurements[group_id].items()}
                decision = classify_group(scores, thresholds[name]['min_fill'])
                decision['confidence'] *= alignment['confidence']*quality['confidence']
                decision['bubble_scores'] = measurements[group_id]
                decisions[group_id] = decision
                if decision['status'] in ('ambiguous', 'multiple'):
                    logger.warning("%s %s", group_id, decision['status'])
        result.update(decode_sections(template, decisions))
        result.update(status='ok', thresholds=thresholds, groups=decisions)
        requires_review = any(d['status'] in ('multiple', 'ambiguous') for d in decisions.values())
        requires_review |= any(v['status'] in ('invalid', 'ambiguous', 'multiple') for v in result['phan_3'].values())
        requires_review |= any(v['status'] != 'ok' for v in result['student'].values())
        quality['overall_status'] = 'review_required' if requires_review or experimental else 'ok'
        if debug:
            artifacts['11_bubbles_overlay'] = draw_template(warped, scoring_template, decisions)
            artifacts['12_result_overlay'] = draw_result(warped, scoring_template, decisions, result)
            artifacts['13_grid_overlay'] = draw_grid(warped, scoring_template, decisions)
    except OMRError as exc:
        logger.error("%s: %s", exc.code, exc)
        result.update(status='error', error={'code': exc.code, 'message': str(exc)})
        quality['overall_status'] = 'failed'
        if isinstance(exc, AlignmentError) and exc.diagnostics is not None:
            quality['alignment'] = exc.diagnostics
            if 'alignment' in result:
                result['alignment']['status'] = 'failed'
            if debug and exc.warped is not None:
                artifacts['04_warped'] = exc.warped.copy()
                artifacts['05_alignment'] = draw_alignment(exc.warped, exc.diagnostics)
    result['elapsed_seconds'] = perf_counter()-started
    return result, artifacts
