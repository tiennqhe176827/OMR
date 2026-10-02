import cv2
import numpy as np
from config import DEFAULT, BubbleConfig, MarkerConfig


def grayscale(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()


def preprocess_markers(image: np.ndarray, cfg: MarkerConfig = DEFAULT.marker) -> list[np.ndarray]:
    gray = grayscale(image)
    otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, cfg.adaptive_window, cfg.adaptive_c)
    return [otsu, adaptive]


def preprocess_omr_roi(roi: np.ndarray, cfg: BubbleConfig = DEFAULT.bubble) -> tuple[np.ndarray, np.ndarray]:
    gray = grayscale(roi)
    if cfg.blur_kernel > 1:
        gray = cv2.GaussianBlur(gray, (cfg.blur_kernel, cfg.blur_kernel), 0)
    if cfg.threshold_method == "otsu":
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    elif cfg.threshold_method == "adaptive":
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY_INV, cfg.adaptive_window, cfg.adaptive_c)
    else:
        raise ValueError("threshold_method must be otsu or adaptive")
    if cfg.morphology_kernel > 0:
        kernel = np.ones((cfg.morphology_kernel, cfg.morphology_kernel), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    return gray, binary
