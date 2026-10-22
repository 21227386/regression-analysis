"""Direct MAPE fitting: exact type multipliers, multistart two-variable search.

For fixed slopes, sum(abs(c * base / actual - 1)) is a weighted absolute
loss in c. Its exact minimizer is a weighted median of actual / base,
with weights base / actual. This leaves only two slopes to optimize.
No log-residual or smoothed surrogate replaces the requested objective.
"""
import numpy as np


def _nelder_mead(objective, initial, maxiter=600):
    simplex = np.array([initial, initial + [0.2, 0], initial + [0, 0.2]], dtype=float)
    values = np.array([objective(point) for point in simplex])
    for _ in range(maxiter):
        order = np.argsort(values, kind='stable')
        simplex, values = simplex[order], values[order]
        if np.max(np.abs(simplex[1:] - simplex[0])) < 1e-8 and values[-1] - values[0] < 1e-11:
            return simplex[0], True
        center = simplex[:2].mean(axis=0)
        reflected = center + (center - simplex[2])
        reflected_value = objective(reflected)
        if reflected_value < values[0]:
            expanded = center + 2 * (reflected - center)
            expanded_value = objective(expanded)
            simplex[2], values[2] = (expanded, expanded_value) if expanded_value < reflected_value else (reflected, reflected_value)
        elif reflected_value < values[1]:
            simplex[2], values[2] = reflected, reflected_value
        else:
            outside = reflected_value < values[2]
            contracted = center + 0.5 * ((reflected if outside else simplex[2]) - center)
            contracted_value = objective(contracted)
            if contracted_value < (reflected_value if outside else values[2]):
                simplex[2], values[2] = contracted, contracted_value
            else:
                simplex[1:] = simplex[0] + 0.5 * (simplex[1:] - simplex[0])
                values[1:] = [objective(point) for point in simplex[1:]]
    return simplex[np.argmin(values)], False


def minimize_mape(log_features, log_actual, groups):
    means, scales = log_features.mean(axis=0), log_features.std(axis=0)
    features = (log_features - means) / scales
    masks = [np.asarray(groups) == group for group in sorted(set(groups))]
    within_x, within_y = features.copy(), log_actual.copy()
    for mask in masks:
        within_x[mask] -= features[mask].mean(axis=0)
        within_y[mask] -= log_actual[mask].mean()
    initial = np.linalg.lstsq(within_x, within_y, rcond=None)[0]
    baseline_log = features @ initial
    for mask in masks:
        baseline_log[mask] += (log_actual[mask] - baseline_log[mask]).mean()
    baseline_mape = float(np.mean(np.abs(np.expm1(baseline_log - log_actual))) * 100)
    evaluations = 0

    def evaluate(slopes, details=False):
        nonlocal evaluations
        evaluations += 1
        if not np.isfinite(slopes).all():
            return float('inf')
        relative_log = log_actual - features @ slopes
        intercepts = np.empty(len(log_actual))
        for mask in masks:
            ratios = relative_log[mask]
            order = np.argsort(ratios, kind='stable')
            sorted_ratios = ratios[order]
            with np.errstate(under='ignore'):
                weights = np.exp(sorted_ratios[0] - sorted_ratios)
            median_index = np.searchsorted(np.cumsum(weights), weights.sum() / 2)
            intercepts[mask] = sorted_ratios[min(median_index, len(sorted_ratios) - 1)]
        with np.errstate(over='ignore', under='ignore', invalid='ignore'):
            predicted_log = features @ slopes + intercepts
            loss = float(np.mean(np.abs(np.expm1(predicted_log - log_actual))))
        if details:
            return loss, predicted_log, intercepts
        return loss if np.isfinite(loss) else float('inf')

    best, best_loss = initial.copy(), evaluate(initial)
    converged = best_loss < 1e-12
    if not converged:
        starts = [initial, np.zeros(2)] + [initial + delta for delta in [[.5, 0], [-.5, 0], [0, .5], [0, -.5]]]
        for start in starts:
            candidate, success = _nelder_mead(evaluate, start)
            loss = evaluate(candidate)
            if loss < best_loss:
                best, best_loss = candidate, loss
            converged |= success
    if not converged or not np.isfinite(best_loss):
        raise ValueError('MAPE 최적화가 수렴하지 않았습니다. 입력 자료의 중량·치수·속력을 확인하세요.')
    loss, predicted_log, intercepts = evaluate(best, details=True)
    if loss * 100 > baseline_mape + 1e-8:
        raise ValueError('MAPE 최적화 결과를 검증하지 못했습니다. 입력 자료를 확인하세요.')
    slopes = best / scales
    raw_intercepts = intercepts - means @ slopes
    return slopes, raw_intercepts, predicted_log, baseline_mape, evaluations
