"""All tunable operating thresholds. Defaults require validation on real scans."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MarkerConfig:
    min_area_fraction: float = 0.000025
    max_area_fraction: float = 0.004
    min_side: int = 4
    aspect_min: float = 0.55
    aspect_max: float = 1.8
    min_solidity: float = 0.85
    min_extent: float = 0.55
    min_blackness: float = 0.65
    min_local_contrast: float = 0.25
    min_local_darkness_delta: float = 25.0
    min_solid_ink_fraction: float = 0.85
    polygon_epsilon: float = 0.05
    min_quadrilateral_area_ratio: float = 0.85
    size_ratio: float = 2.5
    # Must stay in step with android_bridge.validate_geometry's 10% floor. A
    # stricter value made the whole sheet undetected as soon as the user held the
    # phone a little further away, which reads as "cannot catch the paper".
    min_quad_area_fraction: float = 0.10
    max_candidates: int = 100
    max_hull_points: int = 20
    border_band: float = 0.22
    adaptive_window: int = 41
    adaptive_c: float = 12
    dedup_distance: float = 0.5


@dataclass(frozen=True)
class GeometryConfig:
    canonical_width: int = 2000
    canonical_height: int = 2800
    orientation_width: int = 400
    orientation_max_error: float = 6.5
    orientation_min_margin: float = 0.25
    edge_threshold: int = 40
    edge_distance_cap: float = 20.0
    min_reference_edges: int = 100
    stable_interior_ratio: float = 0.85
    local_alignment_max_error: float = 3.5
    local_alignment_min_edges: int = 25
    anchor_clahe_clip: float = 2.0
    anchor_clahe_tiles: int = 8
    calibration_corner_margin: float = 0.04
    calibration_max_margin: float = 0.2
    marker_match_radius: float = 30.0
    alignment_max_error: float = 7.0
    alignment_refine_limit: float = 20.0
    affine_min_markers: int = 6
    affine_min_coverage: float = 0.20
    affine_min_inlier_fraction: float = 0.80
    affine_ransac_error: float = 2.5
    affine_max_linear_change: float = 0.03
    affine_max_iterations: int = 2000
    affine_confidence: float = 0.99
    affine_refine_iterations: int = 10
    local_warp_min_markers: int = 12
    local_warp_max_displacement: float = 30.0
    local_warp_min_scale: float = 0.65
    local_warp_max_scale: float = 1.35
    local_warp_min_triangle_area: float = 1.0
    grid_ecc_iterations: int = 80
    grid_ecc_epsilon: float = 1e-5
    grid_ecc_min_correlation: float = 0.5
    grid_max_displacement: float = 18.0
    grid_max_linear_change: float = 0.10
    grid_ecc_blur_kernel: int = 3
    alignment_edge_max: float = 3.0
    min_aux_markers: int = 2
    required_aux_fraction: float = 0.75
    min_homography_determinant: float = 1e-12
    min_polygon_area: float = 1.0


@dataclass(frozen=True)
class BubbleConfig:
    # Sample the central half-radius to exclude thick or slightly offset printed rings.
    inner_radius_ratio: float = 0.50
    annulus_inner: float = 1.25
    annulus_outer: float = 1.75
    background_percentile: float = 80.0
    fill_weight: float = 0.7
    darkness_weight: float = 0.3
    min_mask_area: int = 5
    min_local_contrast: float = 0.08
    uniform_fill_contrast: float = 0.12
    threshold_method: str = "adaptive"
    adaptive_window: int = 35
    adaptive_c: float = 10.0
    blur_kernel: int = 1
    morphology_kernel: int = 0


@dataclass(frozen=True)
class DecisionConfig:
    default_min_fill: float = 0.28
    min_margin: float = 0.12
    min_ratio: float = 1.5
    strong_fill: float = 0.48
    weak_fill: float = 0.12
    auto_min_samples: int = 30
    auto_empty_quantile: float = 0.65
    auto_mad_multiplier: float = 6.0
    auto_min_threshold: float = 0.20
    auto_max_threshold: float = 0.42
    auto_min_spread: float = 0.12
    epsilon: float = 1e-6


@dataclass(frozen=True)
class QualityConfig:
    min_dimension: int = 450
    calibration_min_dimension: int = 1400
    min_blur_score: float = 12.0
    min_contrast: float = 15.0
    dark_clip: int = 5
    bright_clip: int = 250
    max_input_pixels: int = 50_000_000


@dataclass(frozen=True)
class DebugConfig:
    jpeg_quality: int = 92
    line_width: int = 2
    font_scale: float = 0.4
    preview_width: int = 1000
    preview_height: int = 850
    score_crop_padding: float = 1.4


@dataclass(frozen=True)
class Config:
    marker: MarkerConfig = field(default_factory=MarkerConfig)
    geometry: GeometryConfig = field(default_factory=GeometryConfig)
    bubble: BubbleConfig = field(default_factory=BubbleConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)


DEFAULT = Config()
