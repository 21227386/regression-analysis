"""Native Windows desktop GUI. No web server or browser is used."""
import os
from pathlib import Path
import sys
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import wx
import wx.dataview as dv
import wx.lib.scrolledpanel as scrolled
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg, NavigationToolbar2WxAgg
from matplotlib import rcParams, font_manager

from excel_io import read_excel, workbook_bytes
from model import COLUMNS, SHIP_TYPES, example
from workflow import EstimatorSession

NAVY = '#142D4E'
BG = '#F3F6FA'
INK = '#18324F'
ACCENT = '#007B8A'
FONT = Path(__file__).resolve().parent / 'assets' / 'fonts' / 'NanumGothic-Regular.ttf'
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.gdi32.AddFontResourceExW(str(FONT), 0x10, 0)
rcParams['font.family'] = ['NanumGothic'] if FONT.exists() else ['Malgun Gothic', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False


def label(parent, text, size=10, bold=False, color=INK):
    item = wx.StaticText(parent, label=text)
    font = item.GetFont()
    font.SetPointSize(size)
    font.SetWeight(wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL)
    item.SetFont(font)
    item.SetForegroundColour(color)
    return item


def button(parent, text, callback):
    item = wx.Button(parent, label=text)
    item.SetMinSize((-1, 36))
    item.Bind(wx.EVT_BUTTON, callback)
    return item


class Table(dv.DataViewListCtrl):
    def __init__(self, parent):
        super().__init__(parent, style=dv.DV_ROW_LINES | dv.DV_VERT_RULES)

    def show_frame(self, frame):
        self.Freeze()
        try:
            self.DeleteAllItems()
            self.ClearColumns()
            for name in frame.columns:
                title = '순항속력 (not)' if name == '순항속력' else str(name)
                self.AppendTextColumn(title, width=130)
            for row in frame.itertuples(index=False, name=None):
                self.AppendItem([f'{v:,.5g}' if isinstance(v, (float, np.floating)) else str(v) for v in row])
        finally:
            self.Thaw()


class EstimatorFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title='Naval Ship Weight Estimator', size=(1280, 900))
        self.SetMinSize((1020, 740))
        self.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName='NanumGothic'))
        self.session = EstimatorSession()
        self.synthetic = False
        self.source_text = '실적함 엑셀 파일을 불러오세요.'
        self.figure = None
        self.canvas = None
        panel = wx.Panel(self)
        panel.SetBackgroundColour(BG)
        layout = wx.BoxSizer(wx.VERTICAL)
        header = wx.Panel(panel)
        header.SetBackgroundColour(NAVY)
        hs = wx.BoxSizer(wx.VERTICAL)
        hs.Add(label(header, 'Naval Ship Weight Estimator', 23, True, '#FFFFFF'), 0, wx.ALL, 16)
        hs.Add(label(header, '실적함 기반 회귀분석 · 함종별 설계계수 · 설계 함정 중량 추정', 11, False, '#D5E8F6'), 0, wx.LEFT | wx.BOTTOM, 18)
        header.SetSizer(hs)
        layout.Add(header, 0, wx.EXPAND)
        layout.Add(label(panel, '  01  엑셀 자료 입력     →     02  회귀계수 자동 산출     →     03  설계 함정 중량 추정', 11, True), 0, wx.ALL, 16)
        self.notice = label(panel, self.source_text, 10)
        layout.Add(self.notice, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.tabs = wx.Notebook(panel)
        self.build_input()
        self.build_model()
        self.build_design()
        self.build_graph()
        layout.Add(self.tabs, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        panel.SetSizer(layout)
        self.CreateStatusBar()
        self.SetStatusText('준비 | 순항속력 not = knot(노트), 경하중량 tonne, 치수 m | 모든 자료는 이 PC에서 처리됩니다.')
        self.Centre()

    def page(self, title, scroll=False):
        p = scrolled.ScrolledPanel(self.tabs) if scroll else wx.Panel(self.tabs)
        p.SetBackgroundColour('#FFFFFF')
        s = wx.BoxSizer(wx.VERTICAL)
        p.SetSizer(s)
        self.tabs.AddPage(p, title)
        return p, s

    def build_input(self):
        p, s = self.page('1. 실적함 데이터')
        row = wx.BoxSizer(wx.HORIZONTAL)
        for name, callback in [('엑셀 양식 저장', self.save_template), ('실적함 엑셀 불러오기', self.open_excel),
                               ('실적함 자료 추가', self.append_excel), ('현재 입력자료 저장', self.save_input),
                               ('가상 예제 보기', self.load_example)]:
            row.Add(button(p, name, callback), 0, wx.RIGHT, 8)
        s.Add(row, 0, wx.ALL, 16)
        for text in ['① 양식을 저장하여 Excel에서 작성한 뒤 불러오면 회귀계수가 자동으로 계산됩니다.',
                     '필수 열: 함종, 경하중량(tonne), 길이·폭·깊이(m), 순항속력(not). 함명은 선택 항목입니다.',
                     '함종: 구축함 / 호위함 / 고속함 / 지원함. 호위함은 최소 4척과 독립적인 크기·속력 변화가 필요합니다.',
                     '자료가 늘면 기존 자료와 합친 엑셀을 다시 열거나 “실적함 자료 추가”를 사용한 뒤 입력자료를 저장하세요.']:
            s.Add(label(p, text), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.counts = label(p, '불러온 자료 없음', 11, True, ACCENT)
        s.Add(self.counts, 0, wx.LEFT | wx.BOTTOM, 16)
        self.input_table = Table(p)
        self.input_table.show_frame(pd.DataFrame(columns=COLUMNS))
        s.Add(self.input_table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

    def build_model(self):
        p, s = self.page('2. 회귀계수 · 실적 비교')
        s.Add(label(p, '호위함 회귀 → 공통 K, α, β 고정 → 다른 함종의 D_T 추정', 14, True), 0, wx.ALL, 16)
        s.Add(label(p, 'W = S × K × (L×B×H)^α × Vc^β × D_T    |    호위함 D_T=1, Vc=순항속력(not)'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.correction = wx.CheckBox(p, label='로그 역변환 편향 보정(S) 적용')
        self.correction.Bind(wx.EVT_CHECKBOX, self.change_correction)
        row.Add(self.correction, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)
        row.Add(button(p, '계수·실적 비교 엑셀 저장', self.save_report))
        s.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.coefficients = label(p, '실적함 자료를 불러오면 계수가 표시됩니다.', 13, True, ACCENT)
        s.Add(self.coefficients, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.dt_table = Table(p)
        self.dt_table.SetMinSize((-1, 150))
        s.Add(self.dt_table, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.metrics = label(p, '', 11, True)
        s.Add(self.metrics, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.model_warning = label(p, '표시 지표는 학습 자료의 적합 오차이며, 새로운 함정의 예측 성능을 보장하지 않습니다.', 10, False, '#955200')
        s.Add(self.model_warning, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.result_table = Table(p)
        s.Add(self.result_table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

    def build_design(self):
        p, s = self.page('3. 설계 함정 중량 추정', scroll=True)
        self.design_panel = p
        s.Add(label(p, '새 함정의 제원을 입력하세요', 19, True), 0, wx.ALL, 24)
        s.Add(label(p, '실적함에서 산출한 회귀계수와 함종별 D_T를 적용합니다. 경하중량 입력은 필요하지 않습니다.'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        grid = wx.FlexGridSizer(cols=2, vgap=16, hgap=20)
        grid.Add(label(p, '함종', 12), 0, wx.ALIGN_CENTER_VERTICAL)
        self.ship_type = wx.Choice(p, choices=SHIP_TYPES)
        self.ship_type.SetStringSelection('호위함')
        grid.Add(self.ship_type, 0, wx.EXPAND)
        self.inputs = []
        for name, value in [('길이 L (m)', '100'), ('폭 B (m)', '15'), ('깊이 H (m)', '8'), ('순항속력 Vc (not)', '16')]:
            grid.Add(label(p, name, 12), 0, wx.ALIGN_CENTER_VERTICAL)
            field = wx.TextCtrl(p, value=value, size=(250, 34))
            field.Bind(wx.EVT_TEXT, self.clear_prediction)
            self.inputs.append(field)
            grid.Add(field, 0, wx.EXPAND)
        self.ship_type.Bind(wx.EVT_CHOICE, self.clear_prediction)
        s.Add(grid, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        self.estimate_button = button(p, '경하중량 추정', self.estimate)
        self.estimate_button.Enable(False)
        s.Add(self.estimate_button, 0, wx.LEFT | wx.BOTTOM, 24)
        self.prediction = label(p, '— tonne', 34, True, ACCENT)
        s.Add(self.prediction, 0, wx.LEFT | wx.BOTTOM, 24)
        self.prediction_detail = label(p, '실적함 자료를 불러온 뒤 추정할 수 있습니다.', 11)
        s.Add(self.prediction_detail, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        self.prediction_warning = label(p, '', 11, False, '#955200')
        s.Add(self.prediction_warning, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        s.Add(label(p, '순항속력 참고값(not): 구축함 17–20 / 호위함 15–18 / 고속함 15–20 / 지원함 12–15'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        s.Add(label(p, '참고값은 자동 환산이나 입력 제한에 사용하지 않습니다. 최대속력과 혼용하지 마세요.'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        p.SetupScrolling(scroll_x=False)

    def build_graph(self):
        p, s = self.page('4. 그래프 · 3차원 곡면')
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.graph_mode = wx.Choice(p, choices=['실적 중량 vs 예측 중량', '함종별 3차원 곡면', '로그 공간 평면'])
        self.graph_mode.SetSelection(0)
        self.graph_type = wx.Choice(p, choices=SHIP_TYPES)
        self.graph_type.SetStringSelection('호위함')
        for control in [self.graph_mode, self.graph_type]:
            row.Add(control, 0, wx.RIGHT, 12)
            control.Bind(wx.EVT_CHOICE, self.draw_graph)
        s.Add(row, 0, wx.ALL, 16)
        s.Add(label(p, '곡면: X=LBH(m³), Y=순항속력(not), Z=경하중량(tonne). 빨간 점=실적, 선=실적−예측 차이. 마우스로 회전할 수 있습니다.'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.figure = Figure(figsize=(9, 5), facecolor='white', constrained_layout=True)
        self.canvas = FigureCanvasWxAgg(p, wx.ID_ANY, self.figure)
        s.Add(self.canvas, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        self.toolbar = NavigationToolbar2WxAgg(self.canvas)
        self.toolbar.Realize()
        s.Add(self.toolbar, 0, wx.EXPAND)
        self.draw_graph()

    def error(self, message):
        wx.MessageBox(str(message), 'Naval Ship Weight Estimator', wx.OK | wx.ICON_ERROR, self)

    def save_file(self, title, default, payload):
        with wx.FileDialog(self, title, defaultFile=default, wildcard='Excel files (*.xlsx)|*.xlsx',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                path = Path(dialog.GetPath())
                if path.suffix.lower() != '.xlsx':
                    path = path.with_suffix('.xlsx')
                path.write_bytes(payload)
                self.SetStatusText('저장 완료: ' + str(path))

    def save_template(self, event=None):
        try:
            self.save_file('엑셀 입력 양식 저장', '실적함_입력양식.xlsx', workbook_bytes(pd.DataFrame(columns=COLUMNS)))
        except Exception as exc:
            self.error(exc)

    def load_file(self, append=False):
        with wx.FileDialog(self, '실적함 엑셀 선택', wildcard='Excel files (*.xlsx)|*.xlsx', style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
        try:
            with pd.ExcelFile(path, engine='openpyxl') as book:
                sheet = book.sheet_names[0]
                if len(book.sheet_names) > 1:
                    with wx.SingleChoiceDialog(self, '실적함 자료가 있는 시트를 선택하세요.', '자료 시트 선택', book.sheet_names) as choice:
                        if choice.ShowModal() != wx.ID_OK:
                            return
                        sheet = choice.GetStringSelection()
                frame = read_excel(book, sheet)
            if append and self.synthetic:
                raise ValueError('가상 예제와 실제 자료를 합칠 수 없습니다. 실적함 엑셀 불러오기로 실제 자료를 먼저 여세요.')
            with wx.BusyCursor():
                self.session.load(frame, append=append)
                self.synthetic = False
                self.source_text = ('자료 추가: ' if append else '불러온 자료: ') + path.name + ' / ' + sheet
                self.refresh()
            if self.session.issue:
                self.error(self.session.issue)
            else:
                self.tabs.SetSelection(1)
        except Exception as exc:
            self.error(exc)

    def open_excel(self, event=None):
        self.load_file(False)

    def append_excel(self, event=None):
        self.load_file(True)

    def load_example(self, event=None):
        self.session.load(example())
        self.synthetic = True
        self.source_text = '가상 예제 — 실제 함정 자료가 아니며 실제 설계에 사용할 계수가 아닙니다.'
        self.refresh()

    def save_input(self, event=None):
        try:
            self.save_file('현재 입력자료 저장', '실적함_학습자료.xlsx', self.session.input_bytes())
        except Exception as exc:
            self.error(exc)

    def save_report(self, event=None):
        try:
            self.save_file('분석 결과 저장', '경하중량_분석결과.xlsx', self.session.report_bytes())
        except Exception as exc:
            self.error(exc)

    def change_correction(self, event=None):
        self.session.correction = self.correction.GetValue()
        self.session.refit()
        self.refresh()

    def clear_prediction(self, event=None):
        self.prediction.SetLabel('— tonne')
        self.prediction_detail.SetLabel('입력 제원으로 경하중량 추정 버튼을 누르세요.')
        self.prediction_warning.SetLabel('')

    def refresh(self):
        data, fitted = self.session.data, self.session.fitted
        self.notice.SetLabel(self.source_text)
        self.notice.SetForegroundColour('#955200' if self.synthetic else INK)
        self.clear_prediction()
        self.estimate_button.Enable(fitted is not None)
        if data is not None:
            self.input_table.show_frame(data)
            counts = data['함종'].value_counts()
            summary = f'전체 {len(data)}척  |  ' + '  ·  '.join(f'{t} {counts.get(t, 0)}척' for t in SHIP_TYPES)
            duplicate = data.duplicated(subset=COLUMNS[1:]).sum()
            if duplicate:
                summary += f'  |  동일 제원·중량 중복 {duplicate}행: 중복 반영 여부를 확인하세요.'
            self.counts.SetLabel(summary)
        if fitted is None:
            self.coefficients.SetLabel(self.session.issue)
            self.metrics.SetLabel('')
            self.dt_table.show_frame(pd.DataFrame(columns=['함종', 'D_T', '실적선 수']))
            self.result_table.show_frame(pd.DataFrame())
            self.prediction_detail.SetLabel(self.session.issue)
        else:
            self.coefficients.SetLabel(f'K = {fitted.k:.8g}     α = {fitted.alpha:.7g}     β = {fitted.beta:.7g}     S = {fitted.smearing:.7g}')
            self.dt_table.show_frame(fitted.coefficients)
            self.result_table.show_frame(fitted.results)
            self.metrics.SetLabel('   |   '.join(f'{k}: {v:.4g}' for k, v in fitted.metrics.items()))
            warnings = ['학습 자료의 적합 오차이며, 새로운 함정에 대한 검증 성능이 아닙니다.']
            if fitted.condition > 30:
                warnings.append('호위함 자료의 공선성이 높아 계수가 불안정할 수 있습니다.')
            if (fitted.coefficients['실적선 수'] < 5).any():
                warnings.append('일부 함종은 실적함이 5척 미만입니다.')
            self.model_warning.SetLabel(' '.join(warnings))
            self.model_warning.Wrap(1120)
        self.draw_graph()
        self.Layout()
        self.SetStatusText('가상 예제 사용 중' if self.synthetic else ('회귀모형 추정 완료' if fitted else self.session.issue))

    def estimate(self, event=None):
        try:
            values = [float(field.GetValue().strip()) for field in self.inputs]
            ship_type = self.ship_type.GetStringSelection()
            result, outside = self.session.estimate(ship_type, *values)
            self.prediction.SetLabel(f'{result:,.2f} tonne')
            factor = self.session.fitted.coefficients.set_index('함종').loc[ship_type, 'D_T']
            self.prediction_detail.SetLabel(f'{ship_type}  |  D_T = {factor:.6g}  |  경하중량 추정값')
            warning = ('관측 범위를 벗어난 입력: ' + ', '.join(outside) + '. 외삽 결과에 주의하세요.') if outside else ''
            if self.synthetic:
                warning = '가상 예제 계수로 계산한 결과입니다. 실제 설계에 사용하지 마세요. ' + warning
            self.prediction_warning.SetLabel(warning)
            self.prediction_warning.Wrap(1100)
            self.Layout()
            self.design_panel.FitInside()
        except (ValueError, OverflowError) as exc:
            self.clear_prediction()
            self.error(str(exc) if str(exc) else '제원을 유한한 양수로 입력하세요.')

    def draw_graph(self, event=None):
        if self.figure is None:
            return
        self.figure.clear()
        fitted = self.session.fitted
        mode = self.graph_mode.GetSelection()
        ax = self.figure.add_subplot(111, projection='3d' if mode else None)
        if fitted is None:
            if mode:
                ax.text2D(.2, .5, '실적함 엑셀을 불러오면 그래프가 표시됩니다.', transform=ax.transAxes)
            else:
                ax.text(.5, .5, '실적함 엑셀을 불러오면 그래프가 표시됩니다.', ha='center', transform=ax.transAxes)
            self.canvas.draw()
            return
        if mode == 0:
            for typ in SHIP_TYPES:
                subset = fitted.results[fitted.results['함종'] == typ]
                if not subset.empty:
                    ax.scatter(subset['경하중량'], subset['예측중량'], label=typ, s=35, alpha=.85)
            limits = fitted.results[['경하중량', '예측중량']].to_numpy()
            lo, hi = limits.min(), limits.max()
            ax.plot([lo, hi], [lo, hi], '--', color='#73869B', label='실적 = 예측')
            ax.set_xlabel('실적 경하중량 (tonne)')
            ax.set_ylabel('예측 경하중량 (tonne)')
            ax.legend()
            ax.grid(alpha=.2)
        else:
            typ = self.graph_type.GetStringSelection()
            selected = fitted.results[fitted.results['함종'] == typ]
            if selected.empty:
                ax.text2D(.2, .5, typ + ' 실적함 자료가 없습니다.', transform=ax.transAxes)
                self.canvas.draw()
                return
            v = selected['순항속력'].to_numpy()
            volume = (selected['길이'] * selected['폭'] * selected['깊이']).to_numpy()
            def span(a):
                lo, hi = float(a.min()), float(a.max())
                if lo == hi:
                    lo, hi = lo * .95, hi * 1.05
                return np.linspace(lo, hi, 35)
            x, y = np.meshgrid(span(volume), span(v))
            factor = fitted.coefficients.set_index('함종').loc[typ, 'D_T']
            with np.errstate(over='raise', invalid='raise'):
                try:
                    logz = np.log(fitted.k * factor * fitted.smearing) + fitted.alpha * np.log(x) + fitted.beta * np.log(y)
                    z = np.exp(logz)
                except FloatingPointError:
                    ax.text2D(.2, .5, '곡면의 수치 범위를 초과했습니다.', transform=ax.transAxes)
                    self.canvas.draw()
                    return
            transform = np.log if mode == 2 else np.asarray
            xx, yy = transform(x), transform(y)
            ax.plot_surface(xx, yy, logz if mode == 2 else z, cmap='viridis', alpha=.65, linewidth=0)
            ox, oy = transform(volume), transform(v)
            actual, pred = transform(selected['경하중량'].to_numpy()), transform(selected['예측중량'].to_numpy())
            ax.scatter(ox, oy, actual, color='#E7563F', s=30, label='실적 중량')
            for a, b, c, d in zip(ox, oy, actual, pred):
                ax.plot([a, a], [b, b], [c, d], color='#E7563F', alpha=.8)
            ax.set_xlabel('ln(LBH / m³)' if mode == 2 else 'LBH (m³)')
            ax.set_ylabel('ln(Vc / not)' if mode == 2 else '순항속력 (not)')
            ax.set_zlabel('ln(W / tonne)' if mode == 2 else '경하중량 (tonne)')
            ax.set_title(typ + f' · D_T={factor:.5g}')
            ax.legend()
        self.canvas.draw()


def smoke_test(frame, output):
    """Exercise the actual GUI controls, workbook path, refit and prediction."""
    from io import BytesIO
    checks = []
    data = example()
    frame.session.load(read_excel(BytesIO(workbook_bytes(data))))
    frame.source_text = '자동 검증용 가상 자료'
    frame.refresh()
    assert frame.session.fitted is not None
    assert frame.input_table.GetItemCount() == 48
    assert frame.estimate_button.IsEnabled()
    frame.ship_type.SetStringSelection('호위함')
    frame.estimate()
    assert '—' not in frame.prediction.GetLabel()
    checks.append('Workbook load, auto fit, table and prediction: PASS')
    for mode in [0, 1, 2]:
        frame.graph_mode.SetSelection(mode)
        frame.draw_graph()
    checks.append('Comparison chart, 3D surface and log plane: PASS')
    report = frame.session.report_bytes()
    assert len(pd.ExcelFile(BytesIO(report)).sheet_names) == 5
    old_count = len(frame.session.data)
    frame.session.load(data.iloc[:1], append=True)
    frame.refresh()
    assert len(frame.session.data) == old_count + 1
    assert frame.prediction.GetLabel() == '— tonne'
    checks.append('Report export, appended observations, refit and stale result clearing: PASS')
    Path(output).write_text('\n'.join(checks), encoding='utf-8')


def main():
    app = wx.App(False)
    app.SetAppName('Naval Ship Weight Estimator')
    frame = EstimatorFrame()
    frame.Show()
    if os.environ.get('NAVAL_ESTIMATOR_READY'):
        def signal_ready():
            try:
                Path(os.environ['NAVAL_ESTIMATOR_READY']).write_text('ready', encoding='ascii')
            except OSError:
                pass
        wx.CallAfter(signal_ready)
    if '--smoke-test' in sys.argv:
        output = sys.argv[sys.argv.index('--smoke-test') + 1]
        def run_checks():
            try:
                smoke_test(frame, output)
                if '--capture-path' in sys.argv:
                    frame.synthetic = True
                    frame.tabs.SetSelection(2)
                    frame.estimate()
                    frame.Raise()
                    wx.Yield()
                    bitmap = wx.Bitmap(frame.GetSize().width, frame.GetSize().height)
                    dc = wx.MemoryDC(bitmap)
                    pos = frame.GetScreenPosition()
                    dc.Blit(0, 0, bitmap.GetWidth(), bitmap.GetHeight(), wx.ScreenDC(), pos.x, pos.y)
                    dc.SelectObject(wx.NullBitmap)
                    bitmap.SaveFile(sys.argv[sys.argv.index('--capture-path') + 1], wx.BITMAP_TYPE_PNG)
                code = 0
            except Exception:
                Path(output).write_text(traceback.format_exc(), encoding='utf-8')
                code = 1
            frame.Destroy()
            app.ExitMainLoop()
            app.exit_code = code
        wx.CallAfter(run_checks)
    app.MainLoop()
    return getattr(app, 'exit_code', 0)


if __name__ == '__main__':
    raise SystemExit(main())
