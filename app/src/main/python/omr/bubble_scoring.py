from dataclasses import asdict
import numpy as np
from config import DEFAULT, BubbleConfig
from .models import Bubble, BubbleScore
from .errors import ROIError


def bubble_mask(shape: tuple[int, int], center: tuple[float, float], radius: float) -> np.ndarray:
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx-center[0])**2 + (yy-center[1])**2 <= radius**2


def score_bubble(gray_roi, binary_roi, bubble: Bubble,
                 cfg: BubbleConfig = DEFAULT.bubble) -> dict:
    """Bubble coordinates here are BLOCK LOCAL PIXELS, not normalized coordinates."""
    cx, cy, radius = bubble.cx, bubble.cy, bubble.radius
    height, width = gray_roi.shape
    if not (radius <= cx < width-radius and radius <= cy < height-radius):
        raise ROIError(f"Bubble outside block: {bubble.id}")
    outer = radius*cfg.annulus_outer
    x0, y0 = max(0, int(np.floor(cx-outer))), max(0, int(np.floor(cy-outer)))
    x1, y1 = min(width, int(np.ceil(cx+outer))+1), min(height, int(np.ceil(cy+outer))+1)
    local = gray_roi[y0:y1, x0:x1]
    binary = binary_roi[y0:y1, x0:x1]
    center = (cx-x0, cy-y0)
    inner = bubble_mask(local.shape, center, radius*cfg.inner_radius_ratio)
    annulus = bubble_mask(local.shape, center, outer) & ~bubble_mask(local.shape, center, radius*cfg.annulus_inner)
    area = int(inner.sum())
    if area < cfg.min_mask_area or not annulus.any():
        raise ROIError(f"Bubble too small to score: {bubble.id}")
    values = local[inner].astype(float)
    background = max(float(np.percentile(local[annulus], cfg.background_percentile)), 1.0)
    normalized_pixels = np.clip((background-values)/background, 0, 1)
    # Adaptive threshold may erase the center of a uniformly shaded pencil mark:
    # the local threshold window itself becomes dark. Independently strong
    # contrast with the outside annulus recovers that case. Flat shadows still
    # have near-zero normalized contrast and cannot qualify.
    ink = (binary[inner] > 0) | (normalized_pixels >= cfg.uniform_fill_contrast)
    foreground = int(np.sum(ink & (normalized_pixels >= cfg.min_local_contrast)))
    fill = foreground/area
    intensity = float(values.mean())
    darkness = 1-intensity/255
    normalized = float(normalized_pixels.mean())
    score = float(np.clip(cfg.fill_weight*fill + cfg.darkness_weight*normalized, 0, 1))
    return asdict(BubbleScore(fill, intensity, darkness, normalized, foreground, area, score))
