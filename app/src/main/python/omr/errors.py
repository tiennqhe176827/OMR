class OMRError(Exception):
    code = "omr_error"


class MarkerDetectionError(OMRError):
    code = "marker_detection_failed"


class OrientationError(OMRError):
    code = "orientation_failed"


class PerspectiveError(OMRError):
    code = "perspective_failed"


class AlignmentError(OMRError):
    code = "alignment_failed"

    def __init__(self, message, diagnostics=None, warped=None):
        super().__init__(message)
        self.diagnostics = diagnostics
        self.warped = warped


class TemplateError(OMRError):
    code = "invalid_template"


class ROIError(OMRError):
    code = "invalid_roi"


class QualityError(OMRError):
    code = "image_quality_failed"


class BlurError(QualityError):
    code = "image_too_blurry"
