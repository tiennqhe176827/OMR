import cv2
import numpy as np
from config import DEFAULT
from .roi_extraction import iter_groups, pixel_rect

COLORS = {'marker': (0, 255, 255), 'roi': (255, 255, 0), 'blank': (255, 0, 0),
          'ok': (0, 180, 0), 'multiple': (0, 0, 255), 'ambiguous': (0, 165, 255),
          'weak': (180, 0, 180)}


def draw_markers(image, markers, corners=None):
    canvas = image.copy()
    for marker in markers:
        cv2.polylines(canvas, [np.array(marker.polygon, np.int32)], True, COLORS['marker'], 2)
    if corners is not None:
        cv2.polylines(canvas, [np.asarray(corners, np.int32)], True, COLORS['ok'], 3)
        for i, point in enumerate(corners):
            cv2.putText(canvas, str(i), tuple(np.asarray(point, int)), cv2.FONT_HERSHEY_SIMPLEX, 1, COLORS['ok'], 2)
    return canvas


def draw_alignment(image, alignment):
    canvas = image.copy()
    for anchor in alignment['anchors']:
        expected, observed = (tuple(np.round(anchor[k]).astype(int)) for k in ('expected', 'observed'))
        cv2.circle(canvas, expected, 10, COLORS['marker'], 2)
        cv2.line(canvas, expected, observed, COLORS['multiple'], 2)
    error = alignment.get('error_px')
    label = f'{error:.2f}px' if error is not None else 'unavailable'
    color = COLORS['ok'] if alignment['status'] == 'ok' else COLORS['multiple']
    cv2.putText(canvas, f"alignment {alignment['status']} max={label}", (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return canvas


def draw_template(image, template, decisions=None, labels=True):
    canvas = image.copy()
    height, width = canvas.shape[:2]
    for name, rect in template['regions'].items():
        r = pixel_rect(rect, (width, height))
        cv2.rectangle(canvas, (r.x, r.y), (r.x+r.w, r.y+r.h), COLORS['roi'], 2)
        cv2.putText(canvas, name, (r.x, r.y-4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLORS['roi'], 1)
    for _, _, group in iter_groups(template):
        decision = decisions.get(group['id']) if decisions else None
        for bubble in group['bubbles']:
            center = (round(bubble['cx']*width), round(bubble['cy']*height))
            radius = round(bubble['radius']*min(width, height))
            state = 'blank'
            if decision:
                symbol = bubble['symbol']
                selected = decision['selected']
                is_selected = symbol in selected if isinstance(selected, list) else symbol == selected
                if is_selected:
                    state = decision['status']
                elif decision['bubble_states'][symbol] == 'weak':
                    state = 'weak'
                elif decision['status'] == 'ambiguous':
                    state = 'ambiguous'
            cv2.circle(canvas, center, radius, COLORS[state], DEFAULT.debug.line_width)
            if labels:
                cv2.putText(canvas, f"{group['id']}:{bubble['symbol']}", (center[0]+radius, center[1]),
                            cv2.FONT_HERSHEY_SIMPLEX, DEFAULT.debug.font_scale, COLORS[state], 1)
    return canvas


def draw_result(image, template, decisions, result):
    canvas = draw_template(image, template, decisions, labels=False)
    lines = [f"SBD = {result['student']['so_bao_danh']['value']}",
             f"Ma de = {result['student']['ma_de']['value']}"]
    for region, _, group in iter_groups(template):
        if region in ('phan_1', 'phan_2'):
            b = group['bubbles'][0]
            decision = decisions[group['id']]
            text = f"{group['id']}={decision['selected'] or decision['status']}"
            cv2.putText(canvas, text, (round(b['cx']*canvas.shape[1]), round(b['cy']*canvas.shape[0])-12),
                        cv2.FONT_HERSHEY_SIMPLEX, DEFAULT.debug.font_scale, COLORS.get(decision['status'], COLORS['ambiguous']), 1)
    lines.extend(f"P3:Q{q} = {v['value']} ({v['status']})" for q, v in result['phan_3'].items())
    for i, text in enumerate(lines):
        cv2.putText(canvas, text, (30, 35+i*25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 100, 0), 2)
    return canvas


def draw_grid(image, template, decisions=None):
    """Diagnostic cells around configured bubbles; scoring stays inside circles."""
    canvas = image.copy()
    tint = image.copy()
    height, width = image.shape[:2]
    cells = []
    for region in ('sbd', 'ma_de', 'phan_1', 'phan_2', 'phan_3'):
        for block in template[region]['blocks']:
            bubbles = [b for group in block['groups'] for b in group['bubbles']]
            radius = float(np.median([b['radius']*min(width, height) for b in bubbles]))
            def spacing(axis, extent):
                values = sorted(b[axis]*extent for b in bubbles)
                clusters = [[values[0]]]
                for value in values[1:]:
                    if value-clusters[-1][-1] > radius:
                        clusters.append([value])
                    else:
                        clusters[-1].append(value)
                centers = [np.mean(c) for c in clusters]
                return float(np.median(np.diff(centers))) if len(centers) > 1 else radius*3
            dx, dy = spacing('cx', width), spacing('cy', height)
            for group in block['groups']:
                decision = decisions.get(group['id']) if decisions else None
                for b in group['bubbles']:
                    x, y = b['cx']*width, b['cy']*height
                    lo, hi = (round(x-dx/2), round(y-dy/2)), (round(x+dx/2), round(y+dy/2))
                    color, selected = (160, 150, 130), False
                    if decision:
                        value = decision['selected']
                        selected = b['symbol'] in value if isinstance(value, list) else value == b['symbol']
                        if selected:
                            color = COLORS[decision['status']]
                        elif decision['status'] == 'ambiguous' and decision['bubble_states'][b['symbol']] != 'blank':
                            color = COLORS['ambiguous']
                    if selected:
                        cv2.rectangle(tint, lo, hi, color, -1)
                    cells.append((lo, hi, (round(x), round(y)), color, selected, b['radius']*min(width, height)))
    canvas = cv2.addWeighted(tint, .28, canvas, .72, 0)
    for lo, hi, center, color, selected, radius in cells:
        cv2.rectangle(canvas, lo, hi, color, 2 if selected else 1)
        if selected:
            cv2.circle(canvas, center, max(2, round(radius*.65)), color, 2)
    return canvas


def draw_graded_answers(image, result):
    """Color answers by key comparison; unknown/ungraded answers stay distinct."""
    canvas = image.copy()
    details = {(d['section'], str(d['question'])): d
               for d in result.get('grading', {}).get('details', [])}
    def color_for(comparison):
        if comparison is None:
            return (150, 150, 150)
        if comparison.get('correct_min') == comparison.get('correct_max'):
            return (0, 180, 0) if comparison['correct_min'] == 1 else (0, 0, 230)
        return (0, 165, 255)
    for section, prefix in [('phan_1', 'P1'), ('phan_2', 'P2'), ('phan_3', 'P3')]:
        for q, answer in result.get(section, {}).items():
            entries = answer.items() if section == 'phan_2' else [(None, answer)]
            detail = details.get((section, q))
            for item, decision in entries:
                group_id = f'{prefix}:Q{q}' + (f':{item}' if item else '')
                groups = [v for k, v in result.get('groups', {}).items()
                          if k == group_id or (section == 'phan_3' and k.startswith(group_id+':'))]
                measurements = [b for g in groups for b in g.get('bubble_scores', {}).values()
                                if 'center_canonical' in b]
                if not measurements:
                    continue
                comparison = detail.get('statements', {}).get(item) if detail and item else detail
                color = color_for(comparison)
                low = np.min([np.array(b['center_canonical'])-b['radius_px']*1.4 for b in measurements], axis=0)
                high = np.max([np.array(b['center_canonical'])+b['radius_px']*1.4 for b in measurements], axis=0)
                cv2.rectangle(canvas, tuple(np.round(low).astype(int)), tuple(np.round(high).astype(int)), color, 3)
                manual = decision.get('source') == 'manual'
                if manual:
                    value = decision.get('value' if section == 'phan_3' else 'answer', '')
                    cv2.putText(canvas, f'MANUAL: {value}', (round(low[0]), round(low[1])-5),
                                cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
                if section == 'phan_3' and manual:
                    continue
                for group in groups:
                    selected = decision.get('answer') if section != 'phan_3' else group.get('selected')
                    selected = selected if isinstance(selected, list) else [selected]
                    for symbol in selected:
                        bubble = group.get('bubble_scores', {}).get(symbol)
                        if bubble:
                            center = tuple(round(x) for x in bubble['center_canonical'])
                            cv2.circle(canvas, center, max(3, round(bubble['radius_px'])), color, 3)
    return canvas
