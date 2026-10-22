"""Interactive mass surface for a fixed ship-type factor."""
import numpy as np
import plotly.graph_objects as go


def mass_surface(fitted, ship_type, logarithmic=False):
    selected = fitted.results[fitted.results['함종'] == ship_type]
    if selected.empty:
        raise ValueError('선택 함종의 실적선 자료가 없습니다.')
    factor = float(fitted.coefficients.set_index('함종').loc[ship_type, 'D_T'])
    volumes = (selected['길이'] * selected['폭'] * selected['깊이']).to_numpy()
    speeds = selected['순항속력'].to_numpy()

    def axis_grid(values):
        low, high = float(values.min()), float(values.max())
        if low == high:
            low, high = low * .95, high * 1.05
        return np.linspace(low, high, 45)

    x, y = np.meshgrid(axis_grid(volumes), axis_grid(speeds))
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        try:
            log_z = (np.log(fitted.k) + np.log(factor) + np.log(fitted.smearing)
                     + fitted.alpha*np.log(x) + fitted.beta*np.log(y))
            z = np.exp(log_z)
        except FloatingPointError as exc:
            raise ValueError('곡면의 수치 범위를 초과했습니다. 자료와 계수를 확인하세요.') from exc
    transform = np.log if logarithmic else np.asarray
    sx, sy, sz = transform(x), transform(y), log_z if logarithmic else z
    ox, oy = transform(volumes), transform(speeds)
    actual = transform(selected['경하중량'].to_numpy())
    predicted = transform(selected['예측중량'].to_numpy())
    fig = go.Figure(go.Surface(x=sx, y=sy, z=sz, opacity=.7, colorscale='Viridis',
                              name='회귀 곡면', colorbar={'title': 'ln(W)' if logarithmic else 'W (tonne)'},
                              hovertemplate='X: %{x:.3f}<br>Y: %{y:.3f}<br>Z: %{z:.3f}<extra>예측 곡면</extra>'))
    fig.add_trace(go.Scatter3d(x=ox, y=oy, z=actual, mode='markers+text', name='실적 중량',
                               text=selected['함명'].tolist(), textposition='top center', marker={'size': 5, 'color': '#ef553b'},
                               hovertemplate='%{text}<br>X: %{x:.3f}<br>Y: %{y:.3f}<br>Z: %{z:.3f}<extra>실적</extra>'))
    fig.add_trace(go.Scatter3d(x=ox, y=oy, z=predicted, mode='markers+text', name='예측 중량',
                               text=selected['함명'].tolist(), textposition='bottom center',
                               marker={'size': 3, 'color': '#163d78'}))
    lx, ly, lz = [], [], []
    for a, b, c, d in zip(ox, oy, actual, predicted):
        lx.extend([a, a, None]); ly.extend([b, b, None]); lz.extend([c, d, None])
    fig.add_trace(go.Scatter3d(x=lx, y=ly, z=lz, mode='lines', name='실적−예측 차이',
                               line={'color': '#ef553b', 'width': 3}, hoverinfo='skip'))
    titles = ['ln(LBH / m³)', 'ln(V / kn)', 'ln(W / tonne)'] if logarithmic else ['LBH (m³)', '순항속력 V (kn)', '경하중량 W (tonne)']
    fig.update_layout(title=f'{ship_type} · D_T = {factor:.6g}' + (' · 로그 공간 평면' if logarithmic else ''),
                      scene={'xaxis_title': titles[0], 'yaxis_title': titles[1], 'zaxis_title': titles[2]},
                      height=680, margin={'l': 0, 'r': 0, 'b': 0, 't': 55}, legend={'orientation': 'h'})
    return fig
