from copy import deepcopy


def aggregate_status(columns: list[dict]) -> str:
    statuses = [c['status'] for c in columns]
    if all(s == 'blank' for s in statuses):
        return 'blank'
    for status in ('multiple', 'invalid', 'ambiguous'):
        if status in statuses:
            return status
    return 'ambiguous' if 'blank' in statuses else 'ok'


def decode_identifier(columns: list[dict]) -> dict:
    columns = sorted(deepcopy(columns), key=lambda c: c['column'])
    status = aggregate_status(columns)
    for column in columns:
        column['value'] = column['selected'] if column['status'] == 'ok' else None
    return {'value': ''.join(c['value'] for c in columns) if status == 'ok' else None,
            'status': status, 'confidence': min(c['confidence'] for c in columns), 'columns': columns}


def decode_short_answer(columns: list[dict], symbol_rules: dict) -> dict:
    columns = sorted(deepcopy(columns), key=lambda c: c['column'])
    for col in columns:
        col['symbol'] = col['selected'] if col['status'] == 'ok' else None
    status = aggregate_status(columns)
    result = {'value': None, 'status': status, 'confidence': min(c['confidence'] for c in columns),
              'columns': columns}
    if status in ('multiple', 'invalid') or any(c['status'] == 'ambiguous' for c in columns):
        return result
    if status == 'blank':
        return result
    active = columns[:]
    if symbol_rules['blank_policy'] == 'trim_edges':
        while active and active[0]['status'] == 'blank':
            active.pop(0)
        while active and active[-1]['status'] == 'blank':
            active.pop()
    if any(c['status'] != 'ok' for c in active):
        result.update(status='invalid', reason='blank_inside_value_or_forbidden')
        return result
    tokens = [c['symbol'] for c in active]
    minus, decimal = symbol_rules['minus'], symbol_rules['decimal']
    digits = set(symbol_rules['digits'])
    if minus is not None and minus in tokens:
        if tokens.count(minus) != 1 or tokens[0] != minus:
            result.update(status='invalid', reason='invalid_sign_position')
            return result
        numeric = tokens[1:]
    else:
        numeric = tokens[:]
    if not numeric:
        result.update(status='invalid', reason='missing_digits')
        return result
    if decimal is not None and decimal in numeric:
        if numeric.count(decimal) != 1 or numeric[0] == decimal or numeric[-1] == decimal:
            result.update(status='invalid', reason='invalid_decimal_position')
            return result
    if not all(t in digits or (decimal is not None and t == decimal) for t in numeric):
        result.update(status='invalid', reason='unsupported_numeric_symbol')
        return result
    result.update(value=''.join(tokens), status='ok', confidence=min(c['confidence'] for c in active))
    return result


def decode_sections(template: dict, decisions: dict[str, dict]) -> dict:
    from .roi_extraction import iter_groups
    identifiers = {'sbd': [], 'ma_de': []}
    part1, part2, part3 = {}, {}, {str(q): [] for q in range(1, 7)}
    for region, _, group in iter_groups(template):
        value = deepcopy(decisions[group['id']])
        if region in identifiers:
            value['column'] = group['column']
            identifiers[region].append(value)
        elif region == 'phan_1':
            value['answer'] = value['selected']
            part1[str(group['question'])] = value
        elif region == 'phan_2':
            value['answer'] = value['selected']
            part2.setdefault(str(group['question']), {})[group['item']] = value
        else:
            value['column'] = group['column']
            part3[str(group['question'])].append(value)
    return {'student': {'so_bao_danh': decode_identifier(identifiers['sbd']),
                        'ma_de': decode_identifier(identifiers['ma_de'])},
            'phan_1': part1, 'phan_2': part2,
            'phan_3': {q: decode_short_answer(cols, template['phan_3']['questions'][q]['symbol_rules'])
                       for q, cols in part3.items()}}
