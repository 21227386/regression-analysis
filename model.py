"""Lightship mass regression. Units: tonne, metre, not."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

COLUMNS = ['함명', '함종', '경하중량', '길이', '폭', '깊이', '순항속력']
NUMERIC = COLUMNS[2:]
SHIP_TYPES = ['구축함', '호위함', '고속함', '지원함']
REFERENCE = '호위함'

@dataclass
class Fit:
    reference: str
    coefficients: pd.DataFrame
    results: pd.DataFrame
    metrics: dict
    k: float
    alpha: float
    beta: float
    smearing: float
    condition: float


def validate(data):
    data = data.copy()
    if '함명' not in data.columns:
        data['함명'] = [f'실적선 {i+1}' for i in range(len(data))]
    else:
        blank = data['함명'].isna() | data['함명'].astype(str).str.strip().eq('')
        data.loc[blank, '함명'] = [f'실적선 {i+1}' for i in np.flatnonzero(blank)]
    if '순항속력' not in data.columns and any(col in data.columns for col in ['최대속력', '최고속력']):
        raise ValueError('기존 최대/최고속력 자료는 자동 환산하지 않습니다. 순항속력(not)을 확인하여 순항속력 열에 입력하세요.')
    missing = set(COLUMNS) - set(data.columns)
    if missing:
        raise ValueError('필수 열 누락: ' + ', '.join(sorted(missing)))
    df = data[COLUMNS].copy()
    if df.empty:
        raise ValueError('실적선 자료를 입력하세요.')
    for col in ['함명', '함종']:
        if df[col].isna().any() or df[col].astype(str).str.strip().eq('').any():
            raise ValueError(f'{col}: 빈 값을 허용하지 않습니다.')
        df[col] = df[col].astype(str).str.strip()
    invalid = sorted(set(df['함종']) - set(SHIP_TYPES))
    if invalid:
        raise ValueError('허용되지 않은 함종: ' + ', '.join(invalid) + '. 구축함, 호위함, 고속함, 지원함 중 하나를 입력하세요.')
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        if not np.isfinite(df[col]).all() or (df[col] <= 0).any():
            raise ValueError(f'{col}: 모든 값은 유한한 양수여야 합니다.')
    return df


def fit(data, reference=REFERENCE, correction=False):
    df = validate(data)
    types = sorted(df['함종'].unique())
    if reference not in types:
        raise ValueError(f'기준 함종 {reference}의 실적선 자료가 필요합니다.')
    others = [t for t in types if t != reference]
    ref = df[df['함종'] == reference]
    if len(ref) < 4:
        raise ValueError(f'{reference} 자료가 최소 4척 필요합니다. 다양한 크기·속력 자료를 입력하세요.')
    def design(frame):
        volume = np.log(frame['길이'].to_numpy()) + np.log(frame['폭'].to_numpy()) + np.log(frame['깊이'].to_numpy())
        return np.column_stack([np.ones(len(frame)), volume, np.log(frame['순항속력'])])
    x = design(ref)
    z = x.copy()
    scale = z[:, 1:].std(axis=0)
    if (scale == 0).any():
        raise ValueError(f'{reference} 크기 또는 속력이 일정하여 계수를 구분할 수 없습니다.')
    z[:, 1:] = (z[:, 1:] - z[:, 1:].mean(axis=0)) / scale
    if np.linalg.matrix_rank(z) < 3:
        raise ValueError(f'{reference} 변수 간 완전한 선형관계로 계수를 구분할 수 없습니다.')
    y = np.log(ref['경하중량'].to_numpy())
    coef = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ coef
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        try:
            k = float(np.exp(coef[0]))
            smear = float(np.mean(np.exp(residual))) if correction else 1.0
            log_base = design(df) @ coef + np.log(smear)
            log_ratio = np.log(df['경하중량'].to_numpy()) - log_base
            factors = [1.0] + [float(np.exp(log_ratio[(df['함종'] == t).to_numpy()].mean())) for t in others]
            mapping = dict(zip([reference] + others, factors))
            predicted = np.exp(log_base + np.log(df['함종'].map(mapping).to_numpy()))
        except FloatingPointError as exc:
            raise ValueError('계수 또는 예측값의 수치 범위를 초과했습니다. 자료의 단위와 공선성을 확인하세요.') from exc
    out = df.copy()
    out['예측중량'] = predicted
    out['오차'] = predicted - df['경하중량']
    out['오차율(%)'] = out['오차'] / df['경하중량'] * 100
    out['절대오차율(%)'] = out['오차율(%)'].abs()
    actual = df['경하중량'].to_numpy()
    sst = np.sum((actual - actual.mean()) ** 2)
    metrics = {'MAE (tonne)': float(np.mean(np.abs(predicted-actual))),
               'RMSE (tonne)': float(np.sqrt(np.mean((predicted-actual)**2))),
               'MAPE (%)': float(np.mean(np.abs(predicted-actual)/actual)*100),
               'R² (중량 기준)': float(1-np.sum((predicted-actual)**2)/sst) if sst > 0 else float('nan')}
    coeff = pd.DataFrame({'함종': [reference] + others, 'D_T': factors})
    coeff['실적선 수'] = coeff['함종'].map(df['함종'].value_counts())
    return Fit(reference, coeff, out, metrics, k, float(coef[1]), float(coef[2]), smear, float(np.linalg.cond(z)))


def predict(fitted, ship_type, length, beam, depth, speed):
    values = np.array([length, beam, depth, speed], dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('치수와 속력은 유한한 양수여야 합니다.')
    factor = fitted.coefficients.set_index('함종')['D_T']
    if ship_type not in factor.index:
        raise ValueError('학습 자료에 없는 함종입니다.')
    with np.errstate(over='raise', invalid='raise'):
        try:
            result = float(np.exp(np.log(fitted.k) + fitted.alpha*np.log(values[:3]).sum()
                                  + fitted.beta*np.log(speed) + np.log(factor[ship_type])) * fitted.smearing)
        except FloatingPointError as exc:
            raise ValueError('예측 범위를 초과했습니다.') from exc
    return result


def example():
    """Synthetic demonstration only; not real ship data."""
    rng = np.random.default_rng(42)
    rows = []
    for typ, factor in [('호위함', 1.0), ('구축함', 1.25), ('고속함', .85), ('지원함', 1.1)]:
        for i in range(12):
            l, b, h, v = rng.uniform(70, 150), rng.uniform(10, 20), rng.uniform(6, 12), rng.uniform(*{'구축함': (17,20), '호위함': (15,18), '고속함': (15,20), '지원함': (12,15)}[typ])
            w = .035 * (l*b*h)**1.05 * v**.25 * factor * np.exp(rng.normal(0, .045))
            rows.append([f'{typ}-{i+1}', typ, w, l, b, h, v])
    return pd.DataFrame(rows, columns=COLUMNS)
