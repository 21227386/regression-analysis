"""Render Times-compatible mathematical artwork with exact subscripts/Greek glyphs."""
from pathlib import Path
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

ROOT = Path(__file__).resolve().parents[1] / 'assets/images'
ROOT.mkdir(parents=True, exist_ok=True)

def render(name, expression, size, fontsize, color='#18324F'):
    figure = Figure(figsize=size, dpi=220, facecolor='none')
    FigureCanvasAgg(figure)
    axes = figure.add_axes([0, 0, 1, 1])
    axes.axis('off')
    axes.text(.5, .5, expression, fontsize=fontsize, color=color, va='center', ha='center', math_fontfamily='stix')
    figure.savefig(ROOT / name, transparent=True, dpi=220)

render('regression_equation.png', r'$W_{LS}=K\,(LBH)^{\alpha}\,V_c^{\beta}\,D_T$', (7.2, 1.05), 34)
for name, expression in [('K', r'$K$'), ('alpha', r'$\alpha$'), ('beta', r'$\beta$'), ('DT', r'$D_T$')]:
    render('symbol_' + name + '.png', expression, (1.0, .65), 34)
    render('symbol_' + name + '_light.png', expression, (1.0, .65), 34, '#C0D2E5')
