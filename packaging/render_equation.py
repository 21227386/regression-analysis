"""Render the exact uncorrected model as a transparent, high-resolution asset."""
from pathlib import Path
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

output = Path(__file__).resolve().parents[1] / 'assets/images/regression_equation.png'
output.parent.mkdir(parents=True, exist_ok=True)
figure = Figure(figsize=(7.2, 1.05), dpi=220, facecolor='none')
FigureCanvasAgg(figure)
axes = figure.add_axes([0, 0, 1, 1])
axes.axis('off')
axes.text(.02, .48, r'$W_{LS}=K\,(LBH)^{\alpha}\,V_c^{\beta}\,D_T$',
          fontsize=29, color='#18324F', va='center', ha='left', math_fontfamily='dejavuserif')
figure.savefig(output, transparent=True, dpi=220)
