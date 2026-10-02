"""Template-based optical mark recognition. No OCR or per-sheet circle search."""

def process_exam_sheet(image_path: str, template_path: str, debug: bool = False):
    from .pipeline import process_exam_sheet as process
    return process(image_path, template_path, debug)
