"""Presentation only: no answer inference in the user interface."""
import json

STATUS_LABELS = {'ok': 'Đã đọc', 'blank': 'Bỏ trống', 'multiple': 'Tô nhiều ô',
                 'ambiguous': 'Chưa rõ', 'invalid': 'Không hợp lệ'}


def answer_text(value):
    if value is None:
        return '—'
    if isinstance(value, list):
        return ' + '.join(answer_text(item) for item in value)
    return {'Dung': 'Đúng', 'Sai': 'Sai'}.get(str(value), str(value))


def result_rows(result):
    rows = {'phan_1': [], 'phan_2': [], 'phan_3': [], 'student': []}
    if result.get('status') != 'ok':
        return rows
    for section in ('phan_1', 'phan_2', 'phan_3'):
        for question, entry in sorted(result[section].items(), key=lambda pair: int(pair[0])):
            items = entry.items() if section == 'phan_2' else [(None, entry)]
            for item, decision in items:
                label = f'Câu {question}' + (f' · {item}' if item else '')
                group = f'P1:Q{question}' if section == 'phan_1' else f'P2:Q{question}:{item}' if section == 'phan_2' else f'P3:Q{question}'
                rows[section].append({'id': group, 'label': label, 'status': decision['status'],
                    'values': (label, answer_text(decision.get('answer', decision.get('value'))),
                               STATUS_LABELS.get(decision['status'], decision['status']), f"{decision['confidence']:.2f}")})
    for name, prefix in [('so_bao_danh', 'SBD'), ('ma_de', 'MD')]:
        for column in result['student'][name]['columns']:
            label = f'{"SBD" if prefix == "SBD" else "Mã đề"} · cột {column["column"]}'
            rows['student'].append({'id': f'{prefix}:C{column["column"]}', 'status': column['status'],
                'values': (label, answer_text(column.get('value')), STATUS_LABELS[column['status']], f"{column['confidence']:.2f}")})
    return rows


def decision_detail(result, group_id):
    if group_id.startswith('P3:Q') and ':C' not in group_id:
        data = result['phan_3'][group_id.split('Q')[1]]
    else:
        data = result.get('groups', {}).get(group_id, {})
    return json.dumps(data, ensure_ascii=False, indent=2)
