import numpy as np
from config import DEFAULT, DecisionConfig
from .models import BubbleDecision


def estimate_fill_threshold(all_scores, cfg: DecisionConfig = DEFAULT.decision) -> dict:
    values = np.asarray(all_scores, dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
        raise ValueError("Scores must be finite and within [0,1]")
    result = {'min_fill': cfg.default_min_fill, 'method': 'fallback', 'samples': int(values.size)}
    if len(values) < cfg.auto_min_samples:
        return result
    empty = values[values <= np.quantile(values, cfg.auto_empty_quantile)]
    baseline = float(np.median(empty))
    mad = float(np.median(np.abs(empty-baseline)))
    spread = float(np.max(values)-baseline)
    result.update(empty_median=baseline, empty_mad=mad, spread=spread)
    if spread < cfg.auto_min_spread or baseline > cfg.auto_min_threshold:
        return result
    threshold = baseline+cfg.auto_mad_multiplier*mad+cfg.min_margin
    result.update(min_fill=float(np.clip(threshold, cfg.auto_min_threshold, cfg.auto_max_threshold)),
                  method='median_mad')
    return result


def classify_group(scores: dict[str, float], min_fill: float | None = None,
                   cfg: DecisionConfig = DEFAULT.decision) -> dict:
    if not scores or any(not np.isfinite(v) or not 0 <= v <= 1 for v in scores.values()):
        raise ValueError("A group needs finite scores within [0,1]")
    threshold = cfg.default_min_fill if min_fill is None else min_fill
    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    symbol, best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    margin, ratio = best-second, best/(second+cfg.epsilon)
    strong = [key for key, value in ordered if value >= max(threshold, cfg.strong_fill)]
    selected = None
    if len(strong) >= 2:
        status, selected, confidence = 'multiple', strong, min(scores[s] for s in strong)
    elif best < cfg.weak_fill:
        status, confidence = 'blank', 1-best/max(cfg.weak_fill, cfg.epsilon)
    elif best >= threshold and margin >= cfg.min_margin and ratio >= cfg.min_ratio:
        status, selected = 'ok', symbol
        confidence = min(best, margin/max(best, cfg.epsilon), 1-1/max(ratio, 1))
    else:
        status, confidence = 'ambiguous', 0.0
    decision = BubbleDecision(selected, status, float(np.clip(confidence, 0, 1)), scores).to_dict()
    decision.update(best=best, second_best=second, margin=margin, ratio=ratio, threshold=threshold,
                    bubble_states={key: ('strong' if value >= cfg.strong_fill else
                                         'filled' if value >= threshold else
                                         'weak' if value >= cfg.weak_fill else 'blank')
                                   for key, value in scores.items()})
    return decision
