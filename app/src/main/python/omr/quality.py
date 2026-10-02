import cv2
import numpy as np
from config import DEFAULT, QualityConfig
from .preprocessing import grayscale
from .errors import QualityError, BlurError


def assess_quality(image, cfg: QualityConfig = DEFAULT.quality) -> dict:
    gray = grayscale(image)
    height, width = gray.shape
    metrics = {'width': width, 'height': height,
               'blur_score': float(cv2.Laplacian(gray, cv2.CV_64F).var()),
               'brightness': float(gray.mean()/255), 'contrast': float(gray.std()),
               'dark_clipping': float(np.mean(gray <= cfg.dark_clip)),
               'bright_clipping': float(np.mean(gray >= cfg.bright_clip))}
    metrics['confidence'] = float(min(1, metrics['blur_score']/(cfg.min_blur_score*4),
                                      metrics['contrast']/(cfg.min_contrast*2)))
    return metrics


def validate_quality(metrics: dict, cfg: QualityConfig = DEFAULT.quality) -> None:
    if metrics['width']*metrics['height'] > cfg.max_input_pixels:
        raise QualityError("Image exceeds configured processing size")
    if min(metrics['width'], metrics['height']) < cfg.min_dimension:
        raise QualityError("Image resolution too low")
    if metrics['blur_score'] < cfg.min_blur_score:
        raise BlurError("Laplacian variance below minimum")
    if metrics['contrast'] < cfg.min_contrast:
        raise QualityError("Image contrast too low")
