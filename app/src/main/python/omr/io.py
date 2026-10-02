from pathlib import Path
import cv2
import numpy as np
from .errors import QualityError


def read_image(path: str | Path) -> np.ndarray:
    try:
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    except OSError as exc:
        raise QualityError(f"Cannot read image: {path}") from exc
    if image is None:
        raise QualityError(f"Unsupported or corrupt image: {path}")
    return image


def write_image(path: str | Path, image: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(path.suffix, image)
    if not ok:
        raise OSError(f"Cannot encode {path}")
    buffer.tofile(str(path))
