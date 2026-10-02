import hashlib
import json
import math
from pathlib import Path
import numpy as np
from config import DEFAULT
from .errors import TemplateError, ROIError, PerspectiveError
from .perspective import order_points
from .models import Template
from .roi_extraction import REGION_NAMES, pixel_rect, iter_groups


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_template(data: dict) -> None:
    try:
        if data['template_version'] != '1.0' or data['calibration_status'] not in ('confirmed', 'synthetic', 'experimental'):
            raise ValueError("Template must be calibrated and confirmed")
        if data.get('baseline_policy', 'blank_reference') not in ('blank_reference', 'none'):
            raise ValueError('Unknown baseline policy')
        if data.get('baseline_policy') == 'none' and data['calibration_status'] != 'experimental':
            raise ValueError('Disabling the blank reference baseline requires experimental status')
        if data['calibration_status'] == 'experimental' and not data.get('calibration_notes'):
            raise ValueError('Experimental templates must document their limitations')
        for key in ('template_id', 'created_at', 'description', 'reference_image', 'reference_sha256'):
            if not isinstance(data[key], str) or not data[key]:
                raise ValueError(f"Missing metadata: {key}")
        size = (data['canonical_size']['width'], data['canonical_size']['height'])
        if any(type(v) is not int or v < 100 for v in size):
            raise ValueError("Invalid canonical size")
        for name, count in (('corners', 4), ('auxiliary', DEFAULT.geometry.min_aux_markers)):
            pts = np.asarray(data['markers'][name], float)
            if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < count or (name == 'corners' and len(pts) != count):
                raise ValueError(f"Invalid {name} markers")
            if not np.isfinite(pts).all() or np.any(pts < 0) or np.any(pts > 1) or len(np.unique(pts, axis=0)) != len(pts):
                raise ValueError("Marker points must be distinct and normalized")
        corners = np.asarray(data['markers']['corners'])*size
        auxiliary = np.asarray(data['markers']['auxiliary'])*size
        if not np.allclose(order_points(corners), corners):
            raise ValueError("Canonical corners must be ordered TL, TR, BR, BL")
        if np.min(np.linalg.norm(auxiliary[:, None, :]-corners[None, :, :], axis=2)) <= DEFAULT.geometry.marker_match_radius:
            raise ValueError("Auxiliary markers must be independent of the four corner anchors")
        identities = set()
        addresses = {name: set() for name in REGION_NAMES}
        for region in REGION_NAMES:
            if not data[region]['blocks']:
                raise ValueError(f"No blocks in {region}")
            r = pixel_rect(data['regions'][region], size)
            block_ids = set()
            for block in data[region]['blocks']:
                if block['id'] in block_ids:
                    raise ValueError("Duplicate block id")
                block_ids.add(block['id'])
                b = pixel_rect(block['rect'], (r.w, r.h))
                if not block['groups']:
                    raise ValueError("Empty block")
                for group in block['groups']:
                    if group['id'] in identities:
                        raise ValueError("Duplicate group id")
                    identities.add(group['id'])
                    symbols = [v['symbol'] for v in group['bubbles']]
                    if not symbols or len(set(symbols)) != len(symbols):
                        raise ValueError("Group needs unique symbols")
                    if region in ('sbd', 'ma_de'):
                        address = (group['column'],)
                        expected = data[region]['symbols']
                        if set(symbols) != set(expected):
                            raise ValueError("ID column symbol mismatch")
                    elif region == 'phan_1':
                        address = (group['question'],)
                        if symbols != list('ABCD'):
                            raise ValueError("Part I requires A B C D")
                    elif region == 'phan_2':
                        address = (group['question'], group['item'])
                        if symbols != ['Dung', 'Sai']:
                            raise ValueError("Part II requires Dung, Sai")
                    else:
                        address = (group['question'], group['column'])
                        question = data[region]['questions'][str(group['question'])]
                        if not set(symbols) <= set(question['symbols']):
                            raise ValueError("Part III symbols absent from configured alphabet")
                    if address in addresses[region]:
                        raise ValueError("Duplicate semantic address")
                    addresses[region].add(address)
                    for bubble in group['bubbles']:
                        cx, cy, radius = (float(bubble[k]) for k in ('cx', 'cy', 'radius'))
                        if not all(math.isfinite(v) for v in (cx, cy, radius)) or radius <= 0:
                            raise ValueError("Invalid bubble geometry")
                        x, y, rad = cx*size[0], cy*size[1], radius*min(size)
                        # Entire bubble must fit the real rounded block crop.
                        if not (r.x+b.x+rad <= x <= r.x+b.x+b.w-rad and r.y+b.y+rad <= y <= r.y+b.y+b.h-rad):
                            raise ValueError(f"Bubble outside block: {group['id']}:{bubble['symbol']}")
        for region in ('sbd', 'ma_de'):
            if addresses[region] != {(c,) for c in range(1, data[region]['num_columns']+1)}:
                raise ValueError(f"Incomplete {region} columns")
            if data[region]['symbols'] != list('0123456789'):
                raise ValueError("ID alphabet must be digits")
        if len(data['phan_1']['blocks']) != 4 or addresses['phan_1'] != {(q,) for q in range(1, 41)}:
            raise ValueError("Part I requires four blocks and 40 questions")
        if addresses['phan_2'] != {(q, i) for q in range(1, 9) for i in 'abcd'}:
            raise ValueError("Part II requires 8 x 4 items")
        if set(data['phan_3']['questions']) != set(map(str, range(1, 7))) or len(data['phan_3']['blocks']) != 6:
            raise ValueError("Part III requires six question blocks")
        expected = set()
        for q, definition in data['phan_3']['questions'].items():
            if definition['num_columns'] < 1 or len(set(definition['symbols'])) != len(definition['symbols']):
                raise ValueError("Invalid short-answer dimensions")
            rules = definition['symbol_rules']
            if rules['blank_policy'] not in ('trim_edges', 'forbid'):
                raise ValueError("Unknown blank policy")
            if not rules['digits'] or not set(rules['digits']) <= set(definition['symbols']):
                raise ValueError("Invalid digit alphabet")
            for key in ('minus', 'decimal'):
                if rules[key] is not None and rules[key] not in definition['symbols']:
                    raise ValueError("Punctuation absent from symbols")
            expected.update((int(q), c) for c in range(1, definition['num_columns']+1))
        if addresses['phan_3'] != expected:
            raise ValueError("Incomplete short-answer columns")
    except (KeyError, TypeError, ValueError, ROIError, PerspectiveError, OverflowError) as exc:
        raise TemplateError(str(exc)) from exc


def load_template(path: str) -> Template:
    try:
        file = Path(path).resolve()
        data = json.loads(file.read_text(encoding='utf-8'))
        validate_template(data)
        reference = (file.parent / data['reference_image']).resolve()
        if file_sha256(reference) != data['reference_sha256']:
            raise TemplateError("Reference checksum mismatch; recalibrate after changing reference")
        return Template(data, str(reference))
    except (OSError, ValueError) as exc:
        raise TemplateError(f"Cannot load template: {exc}") from exc


def save_template(path: str | Path, data: dict) -> None:
    validate_template(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
