"""Register printed grids as blocks, without detecting bubbles or choosing marks."""
from copy import deepcopy
import cv2
import numpy as np
from config import DEFAULT
from .orientation import stable_mask
from .roi_extraction import REGION_NAMES, crop, pixel_rect
from .calibration import rect_normalized
from .preprocessing import grayscale
from .errors import AlignmentError


def edge_feature(image):
    gray = grayscale(image).astype(np.float32)/255
    return cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))


def register_grids(warped, reference, template, cfg=DEFAULT.geometry):
    adjusted = deepcopy(template)
    mask = stable_mask(template, reference.shape)
    height, width = warped.shape[:2]
    reports = {}
    for section in REGION_NAMES:
        ref_roi, region = crop(reference, template['regions'][section])
        cur_roi, _ = crop(warped, template['regions'][section])
        mask_roi, _ = crop(mask, template['regions'][section])
        for block in adjusted[section]['blocks']:
            ref, rect = crop(ref_roi, block['rect'])
            cur, _ = crop(cur_roi, block['rect'])
            support, _ = crop(mask_roi, block['rect'])
            identity = np.eye(2, 3, dtype=np.float32)
            key = f"{section}/{block['id']}"
            try:
                correlation, affine = cv2.findTransformECC(edge_feature(ref), edge_feature(cur), identity.copy(),
                    cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,
                    cfg.grid_ecc_iterations, cfg.grid_ecc_epsilon), support, cfg.grid_ecc_blur_kernel)
            except cv2.error:
                raise AlignmentError(f'Printed-grid registration did not converge: {key}')
            offset = np.array([region.x+rect.x, region.y+rect.y])
            centers = np.array([[b['cx']*width, b['cy']*height] for g in block['groups'] for b in g['bubbles']])-offset
            moved = centers@affine[:, :2].T+affine[:, 2]
            displacement = float(np.max(np.linalg.norm(moved-centers, axis=1)))
            if (correlation < cfg.grid_ecc_min_correlation or displacement > cfg.grid_max_displacement
                    or np.linalg.norm(affine[:, :2]-np.eye(2), ord=2) > cfg.grid_max_linear_change
                    or np.linalg.det(affine[:, :2]) <= 0):
                raise AlignmentError(f'Printed-grid registration uncertain: {key}, correlation={correlation:.3f}, shift={displacement:.2f}px')
            radius_scale = float(np.sqrt(np.linalg.det(affine[:, :2])))
            index = 0
            for group in block['groups']:
                for bubble in group['bubbles']:
                    position = moved[index]+offset
                    bubble['cx'], bubble['cy'] = float(position[0]/width), float(position[1]/height)
                    bubble['radius'] *= radius_scale
                    index += 1
            reports[key] = {'correlation': correlation, 'max_displacement_px': displacement,
                            'template_block_to_warped_block': affine.tolist()}
        # Preserve the image coordinate frame and expand crops when refinement
        # moves a bubble toward an old crop edge. Never clip a scoring mask.
        block_bounds = []
        for block in adjusted[section]['blocks']:
            previous = pixel_rect(block['rect'], (region.w, region.h))
            low = np.array([region.x+previous.x, region.y+previous.y], float)
            high = low+[previous.w, previous.h]
            for group in block['groups']:
                for bubble in group['bubbles']:
                    center = np.array([bubble['cx']*width, bubble['cy']*height])
                    pad = bubble['radius']*min(width, height)*DEFAULT.bubble.annulus_outer
                    low, high = np.minimum(low, center-pad), np.maximum(high, center+pad)
            low, high = np.floor(low), np.ceil(high)
            if np.any(low < 0) or np.any(high > [width, height]):
                raise AlignmentError(f'Registered block outside canonical image: {section}')
            block_bounds.append((low, high))
        region_low = np.min([p[0] for p in block_bounds], axis=0)
        region_high = np.max([p[1] for p in block_bounds], axis=0)
        region_size = region_high-region_low
        adjusted['regions'][section] = rect_normalized((*region_low, *region_size), (width, height))
        for block, (low, high) in zip(adjusted[section]['blocks'], block_bounds):
            block['rect'] = rect_normalized((*(low-region_low), *(high-low)), region_size)
    return adjusted, reports
