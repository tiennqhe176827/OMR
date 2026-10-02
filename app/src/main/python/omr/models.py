from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class Status(str, Enum):
    OK = "ok"
    BLANK = "blank"
    MULTIPLE = "multiple"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class NormalizedPoint:
    x: float
    y: float


@dataclass(frozen=True)
class ROI:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Bubble:
    id: str
    symbol: str
    cx: float
    cy: float
    radius: float


@dataclass(frozen=True)
class GridDefinition:
    origin: tuple[float, float]
    column_step: tuple[float, float]
    row_step: tuple[float, float]
    rows: int
    columns: int
    radius: float


@dataclass
class BubbleScore:
    fill_ratio: float
    mean_intensity: float
    darkness: float
    normalized_darkness: float
    foreground_count: int
    area: int
    score: float


@dataclass
class BubbleDecision:
    selected: str | list[str] | None
    status: str
    confidence: float
    scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Template:
    data: dict[str, Any]
    reference_path: str


@dataclass
class OMRResult:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data
