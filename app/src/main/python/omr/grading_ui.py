"""Tk answer-key editor; importing this module never opens a window."""
import tkinter as tk
from tkinter import messagebox, ttk

from omr.grading import PROFILES, identity
from omr.ui_presenter import STATUS_LABELS


def pretty(value):
    return {'Dung': 'Đ', 'Sai': 'S', None: '—'}.get(value, str(value)) if not isinstance(value, list) else '+'.join(value)


def report_text(report):
    key = report['answer_key']
    total = f"{report['score_min']:.2f}"
    if report['score_min'] != report['score_max']:
        total += f" – {report['score_max']:.2f}"
    lines = [f"{key['exam']} · {key['subject']} · Mã {key['code']}",
             f"{key['track']}" if key['track'] else '',
             f"{'ĐIỂM TẠM TÍNH' if report['status'] == 'review_required' else 'ĐIỂM'}: {total} / 10",
             f"Đáp án phiên bản {key.get('revision', 1)} · {key.get('updated_at', '')}",
             *report['review_reasons'], '',
             'Đúng/Sai: đúng 0/1/2/3/4 ý → 0 / 0,10 / 0,25 / 0,50 / 1,00 điểm.',
             'Trống, tô nhiều hoặc không hợp lệ: 0 điểm. Chưa rõ: cần kiểm tra.',
             'Chỉ chấm các câu trong cấu trúc môn và danh sách đã lưu.', '']
    for section, title in [('phan_1', 'PHẦN I'), ('phan_2', 'PHẦN II'), ('phan_3', 'PHẦN III')]:
        summary = report['sections'][section]
        if not summary['maximum']:
            continue
        lines.append(f"{title}: {summary['score_min']:.2f} – {summary['score_max']:.2f} / {summary['maximum']:.2f}")
        for item in report['details']:
            if item['section'] != section:
                continue
            if section == 'phan_2':
                text = ' | '.join(f"{s}: {pretty(a['actual'])}/{pretty(a['expected'])} ({STATUS_LABELS.get(a['status'], 'Thiếu dữ liệu')})"
                                  for s, a in item['statements'].items())
            else:
                text = f"{pretty(item['actual'])} / {pretty(item['expected'])} ({STATUS_LABELS.get(item['status'], 'Thiếu dữ liệu')})"
            score = f"{item['score_min']:.2f}"
            if item['score_min'] != item['score_max']:
                score += f"–{item['score_max']:.2f}"
            lines.append(f"Câu {item['question']}: {text} → {score}đ")
        lines.append('')
    lines.append('Mỗi dòng: bài làm / đáp án. JSON xuất kèm toàn bộ chi tiết và phiên bản đáp án.')
    return '\n'.join(lines)


class AnswerKeyEditor:
    def __init__(self, app):
        self.app = app
        self.exam, self.subject, _, self.track = identity(
            app.exam_var.get(), app.subject_var.get(), '0', app.track_var.get())
        self.revision = None
        self.loaded_code = None
        self.window = tk.Toplevel(app.root)
        self.window.title(f'Đáp án · {self.exam} · {self.subject}')
        self.window.geometry(f'690x{min(760, app.root.winfo_screenheight()-100)}')
        self.window.transient(app.root)
        self.window.grab_set()
        top = ttk.Frame(self.window, padding=14)
        top.pack(fill='x')
        ttk.Label(top, text=f'{self.exam} · {self.subject}' + (f' · {self.track}' if self.track else ''),
                  wraplength=640).pack(anchor='w')
        row = ttk.Frame(top)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='Mã đề:').pack(side='left')
        self.code = tk.StringVar()
        self.code_box = ttk.Combobox(row, textvariable=self.code, width=18)
        self.code_box.pack(side='left', padx=8)
        ttk.Button(row, text='Tải mã đã lưu', command=self.load).pack(side='left')
        ttk.Button(row, text='Mã mới / Xóa form', command=self.reset).pack(side='left', padx=8)
        self.hint = tk.StringVar(value='Nhập đáp án chuẩn của giáo viên rồi lưu. Giữ nguyên số 0 đầu mã đề.')
        ttk.Label(top, textvariable=self.hint, wraplength=640).pack(anchor='w')
        self.fields = {'phan_1': {}, 'phan_2': {}, 'phan_3': {}}
        self.tf_enabled = {}
        n1, n2, n3, short_points = PROFILES[self.subject]
        scroll_frame = ttk.Frame(self.window)
        scroll_frame.pack(fill='both', expand=True, padx=14)
        canvas = tk.Canvas(scroll_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_frame, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = ttk.Frame(canvas, padding=8)
        item = canvas.create_window(0, 0, window=content, anchor='nw')
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
        tabs = ttk.Notebook(content)
        tabs.pack(fill='both', expand=True)
        for section, count, title in [('phan_1', n1, f'Phần I · {n1} × 0,25đ'),
                                      ('phan_2', 6 if self.subject == 'Tin học' else n2, f'Phần II · chấm {n2} câu'),
                                      ('phan_3', n3, f'Phần III · {n3} × {short_points/100:g}đ')]:
            if not count:
                continue
            frame = ttk.Frame(tabs, padding=10)
            tabs.add(frame, text=title)
            if section == 'phan_2' and self.subject == 'Tin học':
                ttk.Label(frame, text='Đánh dấu đúng 4 câu theo đề / định hướng. Không tự chọn câu điểm cao.',
                          wraplength=560).grid(row=0, column=0, columnspan=6, pady=8)
            for q in range(1, count+1):
                # Four-column layout keeps 40 ABCD questions visible without a tall form.
                r, c = (1+(q-1)//4, ((q-1)%4)*2) if section == 'phan_1' else (q+1, 0)
                ttk.Label(frame, text=f'Câu {q}').grid(row=r, column=c, sticky='w', padx=5, pady=5)
                if section == 'phan_2':
                    self.tf_enabled[q] = tk.BooleanVar(value=self.subject != 'Tin học')
                    if self.subject == 'Tin học':
                        ttk.Checkbutton(frame, text='Chấm', variable=self.tf_enabled[q]).grid(row=r, column=1)
                    fields = {}
                    for idx, s in enumerate('abcd'):
                        variable = tk.StringVar()
                        ttk.Combobox(frame, textvariable=variable, values=['Đ', 'S'], state='readonly', width=4).grid(
                            row=r, column=idx+2, padx=6, pady=8)
                        fields[s] = variable
                    self.fields[section][str(q)] = fields
                    for idx, s in enumerate('abcd'):
                        ttk.Label(frame, text=s).grid(row=1, column=idx+2)
                else:
                    variable = tk.StringVar()
                    if section == 'phan_1':
                        widget = ttk.Combobox(frame, textvariable=variable, values=list('ABCD'), state='readonly', width=3)
                    else:
                        widget = ttk.Entry(frame, textvariable=variable, width=22)
                    widget.grid(row=r, column=c+1, padx=(0, 12), pady=5)
                    self.fields[section][str(q)] = variable
        footer = ttk.Frame(self.window, padding=14)
        footer.pack(fill='x')
        ttk.Button(footer, text='Lấy từ phiếu đang mở…', command=self.seed).pack(side='left')
        ttk.Button(footer, text='Lưu đáp án', command=self.save, style='Accent.TButton').pack(side='right')
        self.refresh_codes()

    def refresh_codes(self):
        keys = self.app.key_store.list_keys()
        self.code_box.configure(values=sorted(k['code'] for k in keys if
            (k['exam'], k['subject'], k['track']) == (self.exam, self.subject, self.track)))

    def reset(self):
        self.revision, self.loaded_code = None, None
        self.code.set('')
        for section, fields in self.fields.items():
            for var in fields.values():
                if section == 'phan_2':
                    for v in var.values():
                        v.set('')
                else:
                    var.set('')
        for var in self.tf_enabled.values():
            var.set(self.subject != 'Tin học')
        self.hint.set('Đáp án mới. Hãy nhập mã đề và đủ đáp án cho các câu cần chấm.')

    def fill(self, key):
        self.reset()
        self.code.set(key['code'])
        for section, fields in self.fields.items():
            for q, variable in fields.items():
                answer = key.get(section, {}).get(q)
                if section == 'phan_2':
                    for s, var in variable.items():
                        var.set(pretty((answer or {}).get(s)) if (answer or {}).get(s) else '')
                else:
                    variable.set(answer or '')
        for q, var in self.tf_enabled.items():
            var.set(q in key.get('tf_questions', []))

    def load(self):
        try:
            key = self.app.key_store.load(self.exam, self.subject, self.code.get().strip(), self.track)
            if key is None:
                raise ValueError('Mã đề chưa được lưu. Chọn Mã mới để nhập đáp án.')
            self.fill(key)
            self.revision, self.loaded_code = key['revision'], key['code']
            self.hint.set(f"Đang sửa mã {key['code']} · phiên bản {self.revision}. Bấm Lưu để cập nhật.")
        except (OSError, ValueError) as exc:
            messagebox.showerror('Không tải được đáp án', str(exc), parent=self.window)

    def data(self):
        key = {'schema_version': 1, 'exam': self.exam, 'subject': self.subject, 'track': self.track,
               'code': self.code.get().strip(), 'tf_questions': [q for q, v in self.tf_enabled.items() if v.get()]}
        for section, fields in self.fields.items():
            key[section] = {}
            for q, variable in fields.items():
                if section == 'phan_2':
                    if int(q) in key['tf_questions']:
                        key[section][q] = {s: {'Đ': 'Dung', 'S': 'Sai'}.get(v.get(), '') for s, v in variable.items()}
                else:
                    key[section][q] = variable.get().strip()
        return key

    def save(self):
        try:
            data = self.data()
            revision = self.revision if data['code'] == self.loaded_code else None
            key = self.app.key_store.save(data, revision)
            self.revision, self.loaded_code = key['revision'], key['code']
            self.refresh_codes()
            self.app.refresh_exams()
            self.hint.set(f"Đã lưu mã {key['code']} · phiên bản {key['revision']}. Có thể đóng cửa sổ để chấm bài.")
            self.app.regrade()
            self.app.status_var.set(f"Đã lưu đáp án {self.subject} · mã {key['code']}")
        except (OSError, ValueError) as exc:
            messagebox.showerror('Chưa lưu đáp án', str(exc), parent=self.window)

    def seed(self):
        result = self.app.result
        if not result or result.get('status') != 'ok':
            messagebox.showinfo('Chưa có phiếu', 'Hãy đọc phiếu đáp án của giáo viên trước.', parent=self.window)
            return
        # This is an explicit teacher-key action, never automatic for student uploads.
        if not messagebox.askyesno('Lấy đáp án từ phiếu',
                'Chỉ dùng phiếu này nếu đây là đáp án chuẩn của giáo viên. Lấy dữ liệu vào form để bạn kiểm tra trước khi lưu?',
                parent=self.window):
            return
        code = result.get('student', {}).get('ma_de', {})
        key = {'code': code.get('value') if code.get('status') == 'ok' else '',
               'tf_questions': [q for q, v in self.tf_enabled.items() if v.get()]}
        for section, fields in self.fields.items():
            key[section] = {}
            for q in fields:
                answer = result.get(section, {}).get(q, {})
                if section == 'phan_2':
                    key[section][q] = {s: a.get('answer') for s, a in answer.items() if a.get('status') == 'ok'}
                elif answer.get('status') == 'ok':
                    key[section][q] = answer.get('value' if section == 'phan_3' else 'answer')
        self.fill(key)
        self.hint.set('Đã lấy từ ảnh. Kiểm tra TẤT CẢ đáp án, chọn 4 câu Tin học nếu có, rồi bấm Lưu.')
