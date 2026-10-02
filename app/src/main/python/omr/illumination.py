import cv2
import numpy as np


def normalize_illumination(image_gray: np.ndarray) -> np.ndarray:
    """Normalize large-scale illumination gradients, shadows, and vignetting.

    Uses fast downsampled Gaussian background estimation and division
    to flatten illumination while preserving high-frequency ink marks and bubbles.
    """
    if image_gray.ndim == 3:
        image_gray = cv2.cvtColor(image_gray, cv2.COLOR_BGR2GRAY)
    h, w = image_gray.shape[:2]
    # Downscale for ultra-fast large gaussian blur (~2-4ms)
    small_w = max(64, w // 4)
    small_h = max(64, h // 4)
    small = cv2.resize(image_gray, (small_w, small_h), interpolation=cv2.INTER_AREA)
    # Filter with large kernel proportional to downscaled image
    kernel_size = 51 if small_w >= 100 else 31
    bg_small = cv2.GaussianBlur(small, (kernel_size, kernel_size), 0)
    bg = cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_LINEAR)
    # Background division normalized to [0, 255]
    normalized = cv2.divide(image_gray, np.maximum(bg, 1), scale=240.0)
    return np.clip(normalized, 0, 255).astype(np.uint8)
