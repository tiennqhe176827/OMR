"""Shared geometry construction for interactive calibration and synthetic fixtures."""
from datetime import datetime, timezone
import numpy as np
from .models import GridDefinition
from .coordinate_system import generate_grid


def new_template(template_id: str, size: tuple[int, int], description: str) -> dict:
    return {'template_id': template_id, 'template_version': '1.0',
            'created_at': datetime.now(timezone.utc).isoformat(), 'description': description,
            'calibration_status': 'pending', 'canonical_size': {'width': size[0], 'height': size[1]},
            'markers': {}, 'regions': {},
            'sbd': {'num_columns': 6, 'symbols': list('0123456789'), 'blocks': []},
            'ma_de': {'num_columns': 3, 'symbols': list('0123456789'), 'blocks': []},
            'phan_1': {'blocks': []}, 'phan_2': {'blocks': []},
            'phan_3': {'blocks': [], 'questions': {}}}


def rect_normalized(rect, size):
    x, y, w, h = rect
    return {'x': x/size[0], 'y': y/size[1], 'w': w/size[0], 'h': h/size[1]}


def grid_from_anchors(points, rows: int, columns: int, radius: float) -> GridDefinition:
    first, top_right, bottom_left = np.asarray(points, float)
    column_step = (top_right-first)/max(columns-1, 1) if columns > 1 else np.zeros(2)
    row_step = (bottom_left-first)/max(rows-1, 1) if rows > 1 else np.zeros(2)
    return GridDefinition(tuple(first), tuple(column_step), tuple(row_step), rows, columns, radius)


def make_block(region: str, block_id: str, rect: dict, grid: GridDefinition,
               symbols: list[str], size: tuple[int, int], question_start: int = 1,
               absent: set[tuple[int, int]] | None = None) -> dict:
    """Grid origin/steps are canonical pixels; block rect is normalized to ROI."""
    points = generate_grid(grid)
    absent = absent or set()
    groups = []
    by_column = region in ('sbd', 'ma_de', 'phan_3')
    if len(symbols) != (grid.rows if by_column else grid.columns):
        raise ValueError("Symbol count does not match grid axis")
    for index in range(grid.columns if by_column else grid.rows):
        if region == 'sbd':
            group = {'id': f'SBD:C{index+1}', 'column': index+1}
        elif region == 'ma_de':
            group = {'id': f'MD:C{index+1}', 'column': index+1}
        elif region == 'phan_1':
            group = {'id': f'P1:Q{question_start+index}', 'question': question_start+index}
        elif region == 'phan_2':
            group = {'id': f'P2:Q{question_start}:{"abcd"[index]}', 'question': question_start, 'item': 'abcd'[index]}
        else:
            group = {'id': f'P3:Q{question_start}:C{index+1}', 'question': question_start, 'column': index+1}
        bubbles = []
        for symbol_index, symbol in enumerate(symbols):
            row, col = (symbol_index, index) if by_column else (index, symbol_index)
            if (row, col) in absent:
                continue
            x, y = points[row, col]
            bubbles.append({'symbol': symbol, 'cx': float(x/size[0]), 'cy': float(y/size[1]),
                            'radius': grid.radius/min(size)})
        group['bubbles'] = bubbles
        groups.append(group)
    return {'id': block_id, 'rect': rect, 'groups': groups,
            'grid': {'coordinate_system': 'canonical_normalized',
                     'origin': (np.asarray(grid.origin)/size).tolist(),
                     'column_step': (np.asarray(grid.column_step)/size).tolist(),
                     'row_step': (np.asarray(grid.row_step)/size).tolist(),
                     'rows': grid.rows, 'columns': grid.columns, 'radius': grid.radius/min(size),
                     'absent_cells': [list(cell) for cell in sorted(absent)]}}
