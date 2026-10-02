import math
import numpy as np
from .errors import ROIError
from .models import ROI

REGION_NAMES = ("sbd", "ma_de", "phan_1", "phan_2", "phan_3")


def pixel_rect(rect: dict, size: tuple[int, int]) -> ROI:
    width, height = size
    try:
        x, y, w, h = (float(rect[k]) for k in ('x', 'y', 'w', 'h'))
    except (KeyError, TypeError, ValueError) as exc:
        raise ROIError("Rectangle requires numeric x, y, w, h") from exc
    if not all(math.isfinite(v) for v in (x, y, w, h)) or min(x, y) < 0 or min(w, h) <= 0 or x+w > 1+1e-9 or y+h > 1+1e-9:
        raise ROIError(f"Rectangle outside parent: {rect}")
    x0, y0 = round(x*width), round(y*height)
    x1, y1 = round((x+w)*width), round((y+h)*height)
    if x1 <= x0 or y1 <= y0:
        raise ROIError("Empty crop after rounding")
    return ROI(x0, y0, x1-x0, y1-y0)


def crop(image: np.ndarray, rect: dict) -> tuple[np.ndarray, ROI]:
    roi = pixel_rect(rect, (image.shape[1], image.shape[0]))
    return image[roi.y:roi.y+roi.h, roi.x:roi.x+roi.w].copy(), roi


def extract_main_regions(warped_image, template) -> dict[str, np.ndarray]:
    return {name: crop(warped_image, template['regions'][name])[0] for name in REGION_NAMES}


def extract_blocks(roi, section) -> dict[str, np.ndarray]:
    return {b['id']: crop(roi, b['rect'])[0] for b in section['blocks']}


def extract_part1_blocks(part1_roi, template):
    return extract_blocks(part1_roi, template['phan_1'])


def extract_part3_questions(part3_roi, template):
    return extract_blocks(part3_roi, template['phan_3'])


def iter_groups(template):
    for region in REGION_NAMES:
        for block in template[region]['blocks']:
            for group in block['groups']:
                yield region, block, group
