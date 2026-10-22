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
import wx.lib.buttons as buttons
import wx.lib.scrolledpanel as scrolled
import wx.lib.stattext as stattext
import re
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg, NavigationToolbar2WxAgg
from matplotlib import rcParams, font_manager

from excel_io import EXCEL_HEADERS, read_excel, workbook_bytes
from model import COLUMNS, SHIP_TYPES, example
from workflow import EstimatorSession

NAVY = '#142D4E'
BG = '#F3F6FA'
INK = '#18324F'
ACCENT = '#007B8A'
for font_path in (Path(__file__).resolve().parent / 'assets/fonts').glob('NanumGothic-*.ttf'):
    font_manager.fontManager.addfont(str(font_path))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.gdi32.AddFontResourceExW(str(font_path), 0x10, 0)
ENGLISH_FONT = 'Times New Roman'
# Windows supplies Times New Roman; keep Korean glyph fallback without redistributing Microsoft fonts.
windows_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
for filename in ['times.ttf', 'timesbd.ttf', 'timesi.ttf', 'timesbi.ttf']:
    candidate = windows_fonts / filename
    if candidate.exists():
        font_manager.fontManager.addfont(str(candidate))
rcParams['font.family'] = [ENGLISH_FONT, 'NanumGothic']
rcParams['mathtext.fontset'] = 'stix'
rcParams['axes.unicode_minus'] = False


UI_ENGLISH_FONT = ENGLISH_FONT


def language_runs(text):
    return re.findall(r'[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u4e00-\u9fff]+|[^\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u4e00-\u9fff]+', text)


def run_font(base, text):
    font = wx.Font(base)
    korean = bool(re.search(r'[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u4e00-\u9fff]', text))
    font.SetFaceName('NanumGothic' if korean else UI_ENGLISH_FONT)
    return font


def mixed_extent(dc, text, font):
    width, height = 0, 0
    for part in language_runs(text or ' '):
        dc.SetFont(run_font(font, part))
        w, h = dc.GetTextExtent(part)
        width += w
        height = max(height, h)
    return width, height


def mixed_draw(dc, text, font, x, y, color):
    _, height = mixed_extent(dc, text, font)
    dc.SetTextForeground(color)
    for part in language_runs(text):
        dc.SetFont(run_font(font, part))
        w, h = dc.GetTextExtent(part)
        dc.DrawText(part, int(x), int(y + (height-h)/2))
        x += w


class BilingualLabel(stattext.GenStaticText):
    def DoGetBestSize(self):
        dc = wx.ClientDC(self)
        sizes = [mixed_extent(dc, line, self.GetFont()) for line in self.GetLabel().split('\n')]
        return wx.Size(max((w for w, h in sizes), default=0), sum(h for w, h in sizes))

    def OnPaint(self, event):
        dc = wx.PaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        y = 0
        for line in self.GetLabel().split('\n'):
            w, h = mixed_extent(dc, line, self.GetFont())
            style = self.GetWindowStyleFlag()
            x = max(0, self.GetClientSize().width-w) if style & wx.ALIGN_RIGHT else 0
            mixed_draw(dc, line, self.GetFont(), x, y, self.GetForegroundColour())
            y += h

    def Wrap(self, width):
        dc = wx.ClientDC(self)
        lines = []
        for original in self.GetLabel().split('\n'):
            line = ''
            for char in original:
                if line and mixed_extent(dc, line+char, self.GetFont())[0] > width:
                    lines.append(line.rstrip())
                    line = char.lstrip()
                else:
                    line += char
            lines.append(line)
        self.SetLabel('\n'.join(lines))


def label(parent, text, size=10, bold=False, color=INK):
    item = BilingualLabel(parent, label=text)
    font = item.GetFont()
    font.SetFaceName(UI_ENGLISH_FONT)
    font.SetPointSize(size)
    font.SetWeight(wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL)
    item.SetFont(font)
    item.SetForegroundColour(color)
    return item


class ElevatedButton(buttons.GenButton):
    def InitOtherEvents(self):
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

    def OnPaint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        width, height = self.GetClientSize()
        gc = wx.GraphicsContext.Create(dc)
        base = self.GetBackgroundColour()
        def shade(amount):
            return wx.Colour(*[max(0, min(255, int(channel + amount))) for channel in (base.Red(), base.Green(), base.Blue())])
        down = not self.up
        y = 3 if down else 1
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(30, 57, 77, 65 if self.IsEnabled() else 25)))
        gc.DrawRoundedRectangle(2, 4, max(width-4, 1), max(height-5, 1), 7)
        top, bottom = (shade(-10), shade(12)) if down else (shade(19), shade(-10))
        if not self.IsEnabled():
            top = bottom = wx.Colour('#E6EBF0')
        gc.SetBrush(gc.CreateLinearGradientBrush(0, y, 0, height-5, top, bottom))
        gc.SetPen(wx.Pen(shade(-28) if self.IsEnabled() else '#D5DEE7', 1))
        gc.DrawRoundedRectangle(1, y, max(width-4, 1), max(height-6, 1), 7)
        fg = self.GetForegroundColour() if self.IsEnabled() else wx.Colour('#95A4B3')
        tw, th = mixed_extent(dc, self.GetLabel(), self.GetFont())
        mixed_draw(dc, self.GetLabel(), self.GetFont(), (width-tw)/2 + int(down), (height-th)/2 - 1 + int(down), fg)
        if self.hasFocus and self.IsEnabled():
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.SetPen(wx.Pen('#93C8D0', 1, wx.PENSTYLE_DOT))
            dc.DrawRoundedRectangle(5, 5, max(width-12, 1), max(height-13, 1), 4)


def button(parent, text, callback, kind='secondary'):
    item = ElevatedButton(parent, label=text, style=wx.BORDER_NONE)
    item.SetBezelWidth(2)
    item.SetUseFocusIndicator(True)
    font = item.GetFont()
    font.SetFaceName(UI_ENGLISH_FONT)
    font.SetPointSize(11)
    font.SetWeight(wx.FONTWEIGHT_BOLD)
    item.SetFont(font)
    base, hover, fg = ('#087F8C', '#066C78', '#FFFFFF') if kind == 'primary' else ('#EAF0F6', '#DCE7F0', '#284660')
    item.SetBackgroundColour(base)
    item.SetForegroundColour(fg)
    measurement_dc = wx.ClientDC(item)
    width = mixed_extent(measurement_dc, text, font)[0] + 40
    item.SetMinSize((width, 42))
    item.Bind(wx.EVT_BUTTON, callback)
    def enter(event):
        if item.IsEnabled():
            item.SetBackgroundColour(hover)
            item.Refresh()
        event.Skip()
    def leave(event):
        item.SetBackgroundColour(base)
        item.Refresh()
        event.Skip()
    item.Bind(wx.EVT_ENTER_WINDOW, enter)
    item.Bind(wx.EVT_LEAVE_WINDOW, leave)
    return item


class Card(wx.Panel):
    def __init__(self, parent, color='#FFFFFF'):
        super().__init__(parent)
        self.color = color
        self.SetBackgroundColour(color)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.paint)

    def paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        dc.SetPen(wx.Pen('#DEE6EF' if self.color == '#FFFFFF' else self.color))
        dc.SetBrush(wx.Brush(self.color))
        w, h = self.GetClientSize()
        dc.DrawRoundedRectangle(0, 0, max(w-1, 0), max(h-1, 0), 12)


def symbol_bitmap(key, light=False, size=(34, 26)):
    filename = 'symbol_' + key + ('_light' if light else '') + '.png'
    path = Path(__file__).resolve().parent / 'assets/images' / filename
    return wx.Bitmap(wx.Image(str(path)).Scale(size[0], size[1], wx.IMAGE_QUALITY_HIGH))


def math_caption(parent, key, description, light=False):
    row = wx.BoxSizer(wx.HORIZONTAL)
    image = wx.StaticBitmap(parent, bitmap=symbol_bitmap(key, light))
    row.Add(image, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
    text = label(parent, '(' + description + ')', 10, color='#C0D2E5' if light else '#7A8DA2')
    row.Add(text, 0, wx.ALIGN_CENTER_VERTICAL)
    return row, image, text


class IllustrationPanel(wx.Panel):
    def __init__(self, parent, bitmap):
        super().__init__(parent)
        self.bitmap = bitmap
        self.SetMinSize((bitmap.GetWidth()+20, bitmap.GetHeight()+20))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.paint)

    def GetBitmap(self):
        return self.bitmap

    def paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        w, h = self.GetClientSize()
        dc.SetBrush(wx.Brush('#E2EDF6'))
        dc.SetPen(wx.Pen('#CADFEF', 1))
        dc.DrawRoundedRectangle(0, 0, w-1, h-1, 14)
        dc.DrawBitmap(self.bitmap, (w-self.bitmap.GetWidth())//2, (h-self.bitmap.GetHeight())//2, True)


class Workspace(wx.Simplebook):
    def __init__(self, parent, changed):
        super().__init__(parent)
        self.changed = changed

    def SetSelection(self, index):
        result = super().SetSelection(index)
        self.changed(index)
        return result


class BilingualRenderer(dv.DataViewCustomRenderer):
    def __init__(self, window, centered=False):
        super().__init__('string', dv.DATAVIEW_CELL_INERT, wx.ALIGN_CENTER if centered else wx.ALIGN_LEFT)
        self.centered = centered
        self.window = window
        self.value = ''

    def SetValue(self, value):
        self.value = str(value)
        return True

    def GetValue(self):
        return self.value

    def GetSize(self):
        return wx.Size(100, 23)

    def Render(self, rect, dc, state):
        fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT) if state & dv.DATAVIEW_CELL_SELECTED else wx.Colour(INK)
        w, h = mixed_extent(dc, self.value, self.window.GetFont())
        x = rect.x + max(0, (rect.width-w)//2) if self.centered else rect.x+3
        mixed_draw(dc, self.value, self.window.GetFont(), x, rect.y+max(0, (rect.height-h)//2), fg)
        return True


class Table(dv.DataViewListCtrl):
    def __init__(self, parent, centered=False):
        super().__init__(parent, style=dv.DV_ROW_LINES | dv.DV_VERT_RULES)
        self.centered = centered
        self.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName='NanumGothic'))

    def show_frame(self, frame):
        self.Freeze()
        try:
            self.DeleteAllItems()
            self.ClearColumns()
            for name in frame.columns:
                title = EXCEL_HEADERS.get(name, str(name))
                width = {'함종': 72, 'D_T': 80, '실적선 수': 70}.get(str(name), 130)
                column = dv.DataViewColumn('' if str(name) == 'D_T' else title,
                                           BilingualRenderer(self, self.centered), self.GetColumnCount(), width=width,
                                           align=wx.ALIGN_CENTER if self.centered else wx.ALIGN_LEFT)
                if str(name) == 'D_T':
                    column.SetBitmap(wx.BitmapBundle.FromBitmap(symbol_bitmap('DT', size=(28, 20))))
                self.AppendColumn(column)
            for row in frame.itertuples(index=False, name=None):
                self.AppendItem([f'{v:,.5g}' if isinstance(v, (float, np.floating)) else str(v) for v in row])
        finally:
            self.Thaw()


class EstimatorFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title='Naval Ship Weight Estimator', size=(1280, 900))
        self.SetMinSize((1020, 740))
        self.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName=UI_ENGLISH_FONT))
        self.session = EstimatorSession()
        self.synthetic = False
        self.source_text = '실적함 엑셀 파일을 불러오세요.'
        self.figure = None
        self.canvas = None
        area = wx.GetClientDisplayRect()
        self.SetSize((min(1360, area.width-36), min(900, area.height-48)))
        panel = wx.Panel(self)
        panel.SetBackgroundColour(BG)
        layout = wx.BoxSizer(wx.HORIZONTAL)
        sidebar = wx.Panel(panel)
        sidebar.SetBackgroundColour(NAVY)
        sidebar.SetMinSize((210, -1))
        side = wx.BoxSizer(wx.VERTICAL)
        brand = label(sidebar, 'Naval Ship\nWeight\nEstimator', 22, True, '#FFFFFF')
        side.Add(brand, 0, wx.ALL, 24)
        rule = wx.Panel(sidebar, size=(58, 3))
        rule.SetBackgroundColour('#6FE0D4')
        side.Add(rule, 0, wx.LEFT | wx.BOTTOM, 24)
        side.Add(label(sidebar, 'DESIGN WORKSPACE', 8, True, '#8FA7C1'), 0, wx.LEFT | wx.TOP | wx.BOTTOM, 24)
        self.navigation = []
        titles = [('01', 'Input Data'), ('02', 'Regression Model'), ('03', 'Weight Estimation'), ('04', 'Insights & 3D')]
        for index, (number, name) in enumerate(titles):
            nav = buttons.GenButton(sidebar, label=f'{number}   {name}', style=wx.BORDER_NONE)
            nav.SetBezelWidth(0)
            nav_font = nav.GetFont()
            nav_font.SetFaceName(UI_ENGLISH_FONT)
            nav_font.SetPointSize(11)
            nav_font.SetWeight(wx.FONTWEIGHT_BOLD)
            nav.SetFont(nav_font)
            nav.SetMinSize((186, 48))
            nav.SetForegroundColour('#B9CBE0')
            nav.SetBackgroundColour(NAVY)
            nav.Bind(wx.EVT_BUTTON, lambda event, i=index: self.tabs.SetSelection(i))
            self.navigation.append(nav)
            side.Add(nav, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        side.AddStretchSpacer()
        side.Add(label(sidebar, 'LOCAL ANALYSIS', 8, True, '#70D8CC'), 0, wx.LEFT | wx.BOTTOM, 24)
        side.Add(label(sidebar, '데이터는 이 PC에서만\n처리됩니다.', 9, False, '#B9CBE0'), 0, wx.LEFT | wx.BOTTOM, 24)
        sidebar.SetSizer(side)
        layout.Add(sidebar, 0, wx.EXPAND)
        content = wx.Panel(panel)
        content.SetBackgroundColour(BG)
        body = wx.BoxSizer(wx.VERTICAL)
        heading = wx.BoxSizer(wx.HORIZONTAL)
        title_group = wx.BoxSizer(wx.VERTICAL)
        title_group.Add(label(content, 'NAVAL ENGINEERING  /  LIGHTSHIP WEIGHT', 8, True, '#788BA0'), 0, wx.BOTTOM, 10)
        self.page_heading = label(content, '실적함 데이터', 23, True)
        title_group.Add(self.page_heading)
        heading.Add(title_group, 1)
        self.state = label(content, '●  NO DATA', 10, True, '#7D8DA0')
        self.state.SetMinSize((160, -1))
        title_group.Add(self.state, 0, wx.TOP, 12)
        image_path = Path(__file__).resolve().parent / 'assets/images/ship_weight_illustration.png'
        self.art_width = 366 if self.GetSize().height >= 840 else 330
        image = wx.Image(str(image_path)).Scale(self.art_width, self.art_width//3, wx.IMAGE_QUALITY_HIGH)
        self.header_illustration = IllustrationPanel(content, wx.Bitmap(image))
        heading.Add(self.header_illustration, 0, wx.ALIGN_CENTER_VERTICAL)
        body.Add(heading, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 24)
        self.notice = label(content, self.source_text, 10, color='#6F8398')
        body.Add(self.notice, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.TOP, 18)
        self.tabs = Workspace(content, self.select_page)
        self.build_input()
        self.build_model()
        self.build_design()
        self.build_graph()
        body.Add(self.tabs, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        content.SetSizer(body)
        layout.Add(content, 1, wx.EXPAND)
        panel.SetSizer(layout)
        status = self.CreateStatusBar(2)
        status.SetStatusWidths([-1, 440])
        self.copyright = label(status, 'Copyright by Naval Ship Design Technology Division', 8, color='#6F8398')
        self.copyright.SetWindowStyleFlag(wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE | wx.BORDER_NONE)
        def position_copyright(event=None):
            rect = status.GetFieldRect(1)
            self.copyright.SetSize(rect.x+4, rect.y+2, max(rect.width-16, 0), max(rect.height-3, 0))
            if event:
                event.Skip()
        status.Bind(wx.EVT_SIZE, position_copyright)
        wx.CallAfter(position_copyright)
        self.SetStatusText('순항속력 kn = knot(노트)  ·  중량 tonne  ·  치수 m')
        self.select_page(0)
        self.Centre()

    def select_page(self, index):
        headings = ['실적함 데이터', '회귀모형 · 실적 비교', '설계 함정 중량 추정', '그래프 · 3차원 분석']
        self.page_heading.SetLabel(headings[index])
        for i, nav in enumerate(self.navigation):
            nav.SetBackgroundColour('#215472' if i == index else NAVY)
            nav.SetForegroundColour('#FFFFFF' if i == index else '#B9CBE0')
            nav.Refresh()
        self.Layout()

    def page(self, title, scroll=False):
        p = scrolled.ScrolledPanel(self.tabs) if scroll else wx.Panel(self.tabs)
        p.SetBackgroundColour(BG)
        s = wx.BoxSizer(wx.VERTICAL)
        p.SetSizer(s)
        self.tabs.AddPage(p, title)
        return p, s

    def build_input(self):
        p, s = self.page('Input Data')
        actions = Card(p)
        a = wx.BoxSizer(wx.VERTICAL)
        a.Add(label(actions, 'Input File', 16, True), 0, wx.LEFT | wx.TOP, 22)
        a.Add(label(actions, '양식을 내려받아 실적함 데이터를 작성한 뒤, 업데이트한 Excel 파일을 업로드하세요.', 10, color='#6F8398'), 0, wx.LEFT | wx.RIGHT | wx.TOP, 22)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.template_button = button(actions, 'Download Input File Template', self.save_template)
        self.upload_button = button(actions, 'Input File Upload', self.open_excel, 'primary')
        row.Add(self.template_button, 0, wx.RIGHT, 12)
        row.Add(self.upload_button, 0, wx.RIGHT, 12)
        row.AddStretchSpacer()
        row.Add(button(actions, '가상 예제', self.load_example))
        a.Add(row, 0, wx.EXPAND | wx.ALL, 22)
        actions.SetSizer(a)
        s.Add(actions, 0, wx.EXPAND | wx.BOTTOM, 18)
        statrow = wx.BoxSizer(wx.HORIZONTAL)
        self.stat_values = {}
        for typ in ['전체 실적함'] + SHIP_TYPES:
            tile = Card(p)
            ts = wx.BoxSizer(wx.VERTICAL)
            ts.Add(label(tile, typ, 9, color='#7A8DA2'), 0, wx.LEFT | wx.TOP, 16)
            value = label(tile, '—', 23, True, ACCENT if typ == '전체 실적함' else INK)
            ts.Add(value, 0, wx.LEFT | wx.BOTTOM | wx.TOP, 16)
            tile.SetSizer(ts)
            statrow.Add(tile, 1, wx.RIGHT, 10 if typ != SHIP_TYPES[-1] else 0)
            self.stat_values[typ] = value
        s.Add(statrow, 0, wx.EXPAND | wx.BOTTOM, 18)
        data_card = Card(p)
        ds = wx.BoxSizer(wx.VERTICAL)
        head = wx.BoxSizer(wx.HORIZONTAL)
        self.preview_heading = label(data_card, '실적함 데이터 미리보기', 14, True)
        head.Add(self.preview_heading, 1, wx.ALIGN_CENTER_VERTICAL)
        head.Add(button(data_card, '입력자료 저장', self.save_input))
        ds.Add(head, 0, wx.EXPAND | wx.ALL, 18)
        self.counts = label(data_card, 'Input File Upload로 Excel 파일을 불러오세요.', 9, color='#6F8398')
        ds.Add(self.counts, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.input_table = Table(data_card, centered=True)
        self.input_table.show_frame(pd.DataFrame(columns=COLUMNS))
        ds.Add(self.input_table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 18)
        ds.Add(label(data_card, '중량 tonne  ·  길이/폭/깊이 m  ·  순항속력 kn   |   지원함 포함 · 전체 함종 동시 추정, 함명은 선택 항목', 9, color='#7A8DA2'), 0, wx.ALL, 18)
        data_card.SetSizer(ds)
        s.Add(data_card, 1, wx.EXPAND)

    def build_model(self):
        p, s = self.page('Regression Model', scroll=True)
        self.model_panel = p
        intro = Card(p)
        info = wx.BoxSizer(wx.VERTICAL)
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(label(intro, 'Regression Model', 16, True), 1, wx.ALIGN_CENTER_VERTICAL)
        top.Add(button(intro, '분석 결과 Excel 저장', self.save_report))
        info.Add(top, 0, wx.EXPAND | wx.ALL, 20)
        equation_path = Path(__file__).resolve().parent / 'assets/images/regression_equation.png'
        equation = wx.Image(str(equation_path)).Scale(570, 83, wx.IMAGE_QUALITY_HIGH)
        self.equation_bitmap = wx.StaticBitmap(intro, bitmap=wx.Bitmap(equation))
        info.Add(self.equation_bitmap, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        info.Add(label(intro, 'Vc: 순항속력(kn)    |    기준 함종: 지원함(설계계수 1)', 9, color='#7A8DA2'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.coefficients = label(intro, '실적함 파일을 업로드하면 회귀계수를 자동 산출합니다.', 9, color='#7A8DA2')
        info.Add(self.coefficients, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)
        intro.SetSizer(info)
        s.Add(intro, 0, wx.EXPAND | wx.BOTTOM, 18)
        tiles = wx.BoxSizer(wx.HORIZONTAL)
        self.coefficient_values = {}
        self.coefficient_symbols = {}
        self.coefficient_descriptions = {}
        for name, description in [('K', '기본 회귀계수'), ('alpha', '크기 지수'), ('beta', '속력 지수')]:
            tile = Card(p)
            ts = wx.BoxSizer(wx.VERTICAL)
            caption, image, text = math_caption(tile, name, description)
            self.coefficient_symbols[name] = image
            self.coefficient_descriptions[name] = text
            ts.Add(caption, 0, wx.LEFT | wx.TOP, 14)
            value = label(tile, '—', 23, True, ACCENT)
            ts.Add(value, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 16)
            self.coefficient_values[name] = value
            tile.SetSizer(ts)
            tiles.Add(tile, 1, wx.RIGHT, 10 if name != 'beta' else 0)
        s.Add(tiles, 0, wx.EXPAND | wx.BOTTOM, 18)
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        dt = Card(p)
        dt.SetMinSize((270, -1))
        ds = wx.BoxSizer(wx.VERTICAL)
        caption, self.dt_symbol, _ = math_caption(dt, 'DT', '함종별 설계계수')
        ds.Add(caption, 0, wx.ALL, 18)
        ds.Add(label(dt, '전체 자료로 회귀계수와 동시 산출', 9, color='#7A8DA2'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.dt_table = Table(dt)
        ds.Add(self.dt_table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        dt.SetSizer(ds)
        bottom.Add(dt, 0, wx.EXPAND | wx.RIGHT, 18)
        compare = Card(p)
        cs = wx.BoxSizer(wx.VERTICAL)
        title_row = wx.BoxSizer(wx.HORIZONTAL)
        title_row.Add(label(compare, '실적 중량 비교', 12, True), 1, wx.ALIGN_CENTER_VERTICAL)
        self.comparison_scope = wx.Choice(compare, choices=['전체 함종'] + SHIP_TYPES)
        self.comparison_scope.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName='NanumGothic'))
        self.comparison_scope.SetSelection(0)
        self.comparison_scope.Bind(wx.EVT_CHOICE, self.refresh_comparison)
        title_row.Add(self.comparison_scope, 0)
        cs.Add(title_row, 0, wx.EXPAND | wx.ALL, 18)
        self.metrics = label(compare, '회귀모형을 추정하면 적합 지표가 표시됩니다.', 10, True)
        cs.Add(self.metrics, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        explanations = [
            'MAE (Mean Absolute Error): 평균 절대오차 · tonne',
            'RMSE (Root Mean Squared Error): 제곱평균제곱근오차 · tonne',
            'MAPE (Mean Absolute Percentage Error): 평균 절대백분율오차 · %',
            'R² (Coefficient of Determination): 결정계수 · 1에 가까울수록 적합',
            'MAE / RMSE / MAPE는 작을수록 좋습니다. R²는 음수일 수 있으며,',
            '자료가 1척이거나 실적 중량이 모두 같으면 R²를 산출할 수 없습니다.'
        ]
        for explanation in explanations:
            cs.Add(label(compare, explanation, 9, color='#6F8398'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18 if explanation == explanations[-1] else 6)
        self.model_warning = label(compare, '학습자료에 대한 적합 오차이며 독립 검증 성능이 아닙니다.', 9, color='#A37B35')
        cs.Add(self.model_warning, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.result_table = Table(compare)
        self.result_table.SetMinSize((-1, 220))
        cs.Add(self.result_table, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        compare.SetSizer(cs)
        bottom.Add(compare, 1, wx.EXPAND)
        s.Add(bottom, 1, wx.EXPAND)
        p.SetupScrolling(scroll_x=False)

    def build_design(self):
        p, s = self.page('Weight Estimation', scroll=True)
        self.design_panel = p
        row = wx.BoxSizer(wx.HORIZONTAL)
        params = Card(p)
        ps = wx.BoxSizer(wx.VERTICAL)
        ps.Add(label(params, 'Design Parameters', 16, True), 0, wx.ALL, 22)
        ps.Add(label(params, '새 함정의 함종과 제원을 입력하세요.', 10, color='#6F8398'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 22)
        ps.Add(label(params, '함종', 10, True), 0, wx.LEFT | wx.BOTTOM, 22)
        self.ship_type = wx.Choice(params, choices=SHIP_TYPES, size=(-1, 36))
        self.ship_type.SetFont(wx.Font(11, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName='NanumGothic'))
        self.ship_type.SetStringSelection('호위함')
        ps.Add(self.ship_type, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 22)
        fields = wx.FlexGridSizer(cols=2, vgap=20, hgap=16)
        fields.AddGrowableCol(0, 1)
        fields.AddGrowableCol(1, 1)
        self.inputs = []
        for name, value in [('길이 L (m)', '100'), ('폭 B (m)', '15'), ('깊이 H (m)', '8'), ('순항속력 Vc (kn)', '16')]:
            part = wx.Panel(params)
            part.SetBackgroundColour('#FFFFFF')
            fs = wx.BoxSizer(wx.VERTICAL)
            fs.Add(label(part, name, 9, True), 0, wx.BOTTOM, 8)
            field = wx.TextCtrl(part, value=value, size=(140, 40))
            field.Bind(wx.EVT_TEXT, self.clear_prediction)
            self.inputs.append(field)
            fs.Add(field, 0, wx.EXPAND)
            part.SetSizer(fs)
            fields.Add(part, 1, wx.EXPAND)
        ps.Add(fields, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 22)
        self.ship_type.Bind(wx.EVT_CHOICE, self.clear_prediction)
        self.estimate_button = button(params, '경하중량 추정', self.estimate, 'primary')
        self.estimate_button.Enable(False)
        ps.Add(self.estimate_button, 0, wx.EXPAND | wx.ALL, 22)
        ps.Add(label(params, '경하중량을 입력할 필요 없이 제원만으로 추정합니다.', 9, color='#7A8DA2'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 22)
        params.SetSizer(ps)
        row.Add(params, 1, wx.EXPAND | wx.RIGHT, 18)
        result = Card(p, NAVY)
        rs = wx.BoxSizer(wx.VERTICAL)
        rs.Add(label(result, 'ESTIMATION RESULT', 9, True, '#74D9CD'), 0, wx.LEFT | wx.TOP, 26)
        rs.Add(label(result, '예측 경하중량', 17, True, '#FFFFFF'), 0, wx.LEFT | wx.TOP | wx.BOTTOM, 26)
        self.prediction = label(result, '— tonne', 31, True, '#75E0D3')
        rs.Add(self.prediction, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 26)
        self.prediction_detail = label(result, '실적함 데이터를 업로드하면 추정할 수 있습니다.', 10, color='#C0D2E5')
        rs.Add(self.prediction_detail, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 26)
        factor_row, self.design_dt_symbol, _ = math_caption(result, 'DT', '설계계수', light=True)
        self.design_factor = label(result, '—', 12, True, '#C0D2E5')
        factor_row.Add(self.design_factor, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        rs.Add(factor_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 26)
        self.prediction_warning = label(result, '', 10, color='#F3CB87')
        rs.Add(self.prediction_warning, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 26)
        rs.AddStretchSpacer()
        rs.Add(label(result, '전체 함종 공통 회귀모형 + 함종별 설계계수', 10, True, '#FFFFFF'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 26)
        info = label(result, '학습자료 범위를 벗어난 제원은 외삽으로 안내합니다.\n예측값은 설계 검토를 위한 추정치입니다.', 9, color='#C0D2E5')
        rs.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 26)
        result.SetSizer(rs)
        row.Add(result, 1, wx.EXPAND)
        s.Add(row, 0, wx.EXPAND | wx.BOTTOM, 18)
        reference = Card(p)
        ref = wx.BoxSizer(wx.VERTICAL)
        ref.Add(label(reference, '순항속력 참고 범위  /  kn = knot(노트) · 상륙함은 실제 자료 입력', 10, True), 0, wx.ALL, 18)
        ref.Add(label(reference, '구축함 17–20   ·   호위함 15–18   ·   고속함 15–20   ·   지원함 12–15', 10, color='#6F8398'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        reference.SetSizer(ref)
        s.Add(reference, 0, wx.EXPAND)
        p.SetupScrolling(scroll_x=False)

    def build_graph(self):
        p, s = self.page('4. 그래프 · 3차원 곡면')
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.graph_mode = wx.Choice(p, choices=['실적 중량 vs 예측 중량', '함종별 3차원 곡면', '로그 공간 평면'])
        self.graph_mode.SetSelection(0)
        self.graph_type = wx.Choice(p, choices=SHIP_TYPES)
        self.graph_type.SetFont(wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName='NanumGothic'))
        self.graph_mode.SetFont(self.graph_type.GetFont())
        self.graph_type.SetStringSelection('호위함')
        for control in [self.graph_mode, self.graph_type]:
            row.Add(control, 0, wx.RIGHT, 12)
            control.Bind(wx.EVT_CHOICE, self.draw_graph)
        self.show_ship_names = wx.CheckBox(p, label='함명 표시')
        self.show_ship_names.SetFont(self.graph_type.GetFont())
        self.show_ship_names.SetValue(True)
        self.show_ship_names.Bind(wx.EVT_CHECKBOX, self.draw_graph)
        row.Add(self.show_ship_names, 0, wx.ALIGN_CENTER_VERTICAL)
        s.Add(row, 0, wx.ALL, 16)
        s.Add(label(p, '곡면: X=LBH(m³), Y=순항속력(kn), Z=경하중량(tonne). 빨간 점=실적, 선=실적−예측 차이. 마우스로 회전할 수 있습니다.'), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.figure = Figure(figsize=(9, 5), facecolor='white', constrained_layout=True)
        self.canvas = FigureCanvasWxAgg(p, wx.ID_ANY, self.figure)
        self.canvas.SetMinSize((200, 160))
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
            self.save_file('Download Input File Template', '실적함_입력양식.xlsx', workbook_bytes(pd.DataFrame(columns=COLUMNS)))
        except Exception as exc:
            self.error(exc)

    def load_file(self):
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
            with wx.BusyCursor():
                self.session.load(frame)
                self.synthetic = False
                self.source_text = path.name + '  /  ' + sheet
                self.refresh()
            if self.session.issue:
                self.error(self.session.issue)
            else:
                self.tabs.SetSelection(1)
        except Exception as exc:
            self.error(exc)

    def open_excel(self, event=None):
        self.load_file()

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

    def clear_prediction(self, event=None):
        self.prediction.SetLabel('— tonne')
        self.design_factor.SetLabel('—')
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
            self.stat_values['전체 실적함'].SetLabel(str(len(data)))
            for typ in SHIP_TYPES:
                self.stat_values[typ].SetLabel(str(counts.get(typ, 0)))
            summary = f'전체 {len(data)}척  |  ' + '  ·  '.join(f'{t} {counts.get(t, 0)}척' for t in SHIP_TYPES)
            duplicate = data.duplicated(subset=COLUMNS[1:]).sum()
            if duplicate:
                summary += f'  |  동일 제원·중량 중복 {duplicate}행: 중복 반영 여부를 확인하세요.'
            self.counts.SetLabel(summary)
        if fitted is None:
            self.coefficients.Show()
            self.coefficients.SetLabel(self.session.issue)
            for field in self.coefficient_values.values():
                field.SetLabel('—')
            self.metrics.SetLabel('')
            self.dt_table.show_frame(pd.DataFrame(columns=['함종', 'D_T', '실적선 수']))
            self.result_table.show_frame(pd.DataFrame())
            self.prediction_detail.SetLabel(self.session.issue)
        else:
            for name, value in zip(['K', 'alpha', 'beta'], [fitted.k, fitted.alpha, fitted.beta]):
                self.coefficient_values[name].SetLabel(f'{value:.6g}')
            self.coefficients.Hide()
            self.dt_table.show_frame(fitted.coefficients)
            self.refresh_comparison()
            warnings = [f'전체 {len(data)}척 동시 추정 · 추정계수 {fitted.n_parameters}개 · 잔차 자유도 {fitted.residual_df}.',
                        '학습 자료의 적합 오차이며, 새로운 함정에 대한 검증 성능이 아닙니다.']
            if fitted.residual_df < 5:
                warnings.append('잔차 자유도가 작아 계수가 불안정할 수 있습니다.')
            if fitted.condition > 30:
                warnings.append('전체 자료의 공선성이 높아 계수가 불안정할 수 있습니다.')
            if (fitted.coefficients['실적선 수'] < 5).any():
                warnings.append('일부 함종은 실적함이 5척 미만입니다.')
            self.model_warning.SetLabel(' '.join(warnings))
            self.model_warning.Wrap(max(300, self.result_table.GetParent().GetClientSize().width-36))
        self.state.SetLabel('●  DEMO DATA' if self.synthetic else ('●  MODEL READY' if fitted else '●  DATA REQUIRED'))
        self.state.SetForegroundColour('#B37A23' if self.synthetic else (ACCENT if fitted else '#7D8DA0'))
        self.draw_graph()
        self.Layout()
        self.SetStatusText('가상 예제 사용 중' if self.synthetic else ('회귀모형 추정 완료' if fitted else self.session.issue))

    def refresh_comparison(self, event=None):
        scope = self.comparison_scope.GetStringSelection()
        rows, metrics = self.session.comparison(scope)
        self.result_table.show_frame(rows)
        if not metrics:
            text = f'{scope}: 비교할 자료가 없습니다.'
        else:
            values = [f'{key}: {value:.4g}' + (' tonne' if key in ['MAE', 'RMSE'] else '%' if key == 'MAPE' else '') if np.isfinite(value) else f'{key}: 산출 불가'
                      for key, value in metrics.items()]
            text = f'{scope} · {len(rows)}척\n' + '   |   '.join(values[:2]) + '\n' + '   |   '.join(values[2:])
        self.metrics.SetLabel(text)
        self.model_panel.Layout()
        self.model_panel.FitInside()

    def estimate(self, event=None):
        try:
            values = [float(field.GetValue().strip()) for field in self.inputs]
            ship_type = self.ship_type.GetStringSelection()
            result, outside = self.session.estimate(ship_type, *values)
            self.prediction.SetLabel(f'{result:,.2f} tonne')
            factor = self.session.fitted.coefficients.set_index('함종').loc[ship_type, 'D_T']
            self.prediction_detail.SetLabel(f'{ship_type} (경하중량 추정값)')
            self.design_factor.SetLabel(f'{factor:.6g}')
            warning = ('관측 범위를 벗어난 입력: ' + ', '.join(outside) + '. 외삽 결과에 주의하세요.') if outside else ''
            if self.synthetic:
                warning = '가상 예제 계수로 계산한 결과입니다. 실제 설계에 사용하지 마세요. ' + warning
            self.prediction_warning.SetLabel(warning)
            self.prediction_warning.Wrap(max(250, self.prediction_warning.GetParent().GetClientSize().width-52))
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
                    if self.show_ship_names.GetValue():
                        for name, actual, predicted in zip(subset['함명'], subset['경하중량'], subset['예측중량']):
                            ax.annotate(str(name), (actual, predicted), xytext=(5, 5), textcoords='offset points',
                                        fontsize=8, color=INK, annotation_clip=True)
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
                    logz = np.log(fitted.k * factor) + fitted.alpha * np.log(x) + fitted.beta * np.log(y)
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
            if self.show_ship_names.GetValue():
                for name, a, b, c in zip(selected['함명'], ox, oy, actual):
                    ax.text(a, b, c, '  ' + str(name), fontsize=8, color=INK)
            for a, b, c, d in zip(ox, oy, actual, pred):
                ax.plot([a, a], [b, b], [c, d], color='#E7563F', alpha=.8)
            ax.set_xlabel('ln(LBH / m³)' if mode == 2 else 'LBH (m³)')
            ax.set_ylabel('ln(Vc / kn)' if mode == 2 else '순항속력 (kn)')
            ax.set_zlabel('ln(W / tonne)' if mode == 2 else '경하중량 (tonne)')
            ax.set_title(typ + rf' · $D_T={factor:.5g}$')
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
    assert frame.input_table.GetItemCount() == len(data)
    assert frame.preview_heading.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD
    assert all(frame.input_table.GetColumn(i).GetAlignment() == wx.ALIGN_CENTER
               and frame.input_table.GetColumn(i).GetRenderer().centered
               for i in range(frame.input_table.GetColumnCount()))
    checks.append('Bold preview title and centered preview headers/cells: PASS')
    assert frame.session.fitted.reference == '지원함'
    assert frame.session.fitted.coefficients.set_index('함종').loc['지원함', 'D_T'] == 1.0
    assert frame.estimate_button.IsEnabled()
    frame.ship_type.SetStringSelection('호위함')
    frame.estimate()
    assert '—' not in frame.prediction.GetLabel()
    fitted_before = frame.session.fitted
    for scope in ['전체 함종'] + SHIP_TYPES:
        frame.comparison_scope.SetStringSelection(scope)
        frame.refresh_comparison()
        assert frame.result_table.GetItemCount() == (len(data) if scope == '전체 함종' else 12)
        assert scope in frame.metrics.GetLabel()
        assert frame.session.fitted is fitted_before
    frame.comparison_scope.SetSelection(0)
    frame.refresh_comparison()
    checks.append('Overall and ship-type comparison selector, metrics and unchanged model: PASS')
    checks.append('Workbook load, auto fit, table and prediction: PASS')
    for mode in [0, 1, 2]:
        frame.graph_mode.SetSelection(mode)
        frame.draw_graph()
        expected = data['함명'] if mode == 0 else data.loc[data['함종'] == frame.graph_type.GetStringSelection(), '함명']
        labels = [text.get_text().strip() for text in frame.figure.axes[0].texts]
        assert sorted(labels) == sorted(expected.tolist())
        frame.show_ship_names.SetValue(False)
        frame.draw_graph()
        assert not frame.figure.axes[0].texts
        frame.show_ship_names.SetValue(True)
        frame.draw_graph()
    checks.append('Ship names attached to every observed point in comparison, 3D and log plane; visibility toggle: PASS')
    frame.ship_type.SetStringSelection('상륙함')
    frame.estimate()
    assert '—' not in frame.prediction.GetLabel()
    frame.graph_type.SetStringSelection('상륙함')
    frame.draw_graph()
    frame.ship_type.SetStringSelection('호위함')
    frame.graph_type.SetStringSelection('호위함')
    checks.append('Landing ship prediction, type comparison and 3D graph: PASS')
    checks.append('Comparison chart, 3D surface and log plane: PASS')
    user_mix = pd.concat([data.query("함종 == '지원함'"),
                         data.query("함종 == '구축함'").head(4),
                         data.query("함종 == '호위함'").head(3)], ignore_index=True)
    frame.session.load(read_excel(BytesIO(workbook_bytes(user_mix))))
    frame.refresh()
    assert frame.session.fitted is not None and frame.session.fitted.residual_df == 14
    frame.estimate()
    assert '—' not in frame.prediction.GetLabel()
    frame.session.load(user_mix.head(3))
    frame.refresh()
    assert frame.session.fitted is None and not frame.estimate_button.IsEnabled()
    assert frame.result_table.GetItemCount() == 0
    frame.session.load(data)
    frame.refresh()
    checks.append('Support 12 / destroyer 4 / frigate 3 joint fit, prediction and invalid replacement clearing: PASS')
    report = frame.session.report_bytes()
    assert len(pd.ExcelFile(BytesIO(report)).sheet_names) == 5
    replacement = data.copy()
    replacement['경하중량'] *= 1.1
    frame.session.load(replacement)
    frame.refresh()
    assert len(frame.session.data) == len(replacement)
    assert frame.template_button.GetLabel() == 'Download Input File Template'
    assert frame.upload_button.GetLabel() == 'Input File Upload'
    assert not hasattr(frame, 'append_excel')
    assert not hasattr(frame, 'correction')
    assert not hasattr(frame.session, 'correction')
    assert set(frame.coefficient_values) == {'K', 'alpha', 'beta'}
    assert frame.session.fitted.smearing == 1.0
    assert frame.copyright.GetLabel() == 'Copyright by Naval Ship Design Technology Division'
    assert all(nav.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD for nav in frame.navigation)
    assert frame.equation_bitmap.GetBitmap().IsOk() and frame.header_illustration.GetBitmap().IsOk()
    assert isinstance(frame.upload_button, ElevatedButton)
    if wx.FontEnumerator.IsValidFacename(ENGLISH_FONT):
        assert frame.navigation[0].GetFont().GetFaceName().casefold() == ENGLISH_FONT.casefold()
        assert frame.upload_button.GetFont().GetFaceName().casefold() == ENGLISH_FONT.casefold()
        checks.append('Times New Roman selection: PASS')
    else:
        checks.append('Times New Roman not installed in validation environment; exact font rendering UNVERIFIED (requested in application)')
    assert frame.header_illustration.GetBitmap().GetWidth() >= 330
    assert all(control.GetBitmap().IsOk() for control in frame.coefficient_symbols.values())
    assert all(control.GetLabel().startswith('(') and '/' not in control.GetLabel() for control in frame.coefficient_descriptions.values())
    assert frame.dt_symbol.GetBitmap().IsOk() and frame.design_dt_symbol.GetBitmap().IsOk()

    assert frame.prediction.GetLabel() == '— tonne'
    checks.append('Report export, replacement upload, configured serif font, parenthesized math-image captions, enlarged ship art, copyright, raised buttons and uncorrected model: PASS')
    Path(output).write_text('\n'.join(checks), encoding='utf-8')


def main():
    app = wx.App(False)
    global UI_ENGLISH_FONT
    if wx.FontEnumerator.IsValidFacename(ENGLISH_FONT):
        UI_ENGLISH_FONT = ENGLISH_FONT
    else:
        # Exact Times New Roman is used when installed. Validation on non-Windows
        # hosts may use a Times-compatible serif; no Microsoft font is bundled.
        UI_ENGLISH_FONT = next((name for name in ['Liberation Serif', 'Times', 'Nimbus Roman']
                                if wx.FontEnumerator.IsValidFacename(name)), ENGLISH_FONT)
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
                    frame.source_text = '가상 예제 — 기능 확인용 데이터이며 실제 설계값이 아닙니다.'
                    frame.refresh()
                    frame.tabs.SetSelection(2)
                    frame.estimate()
                    frame.Raise()
                    target = Path(sys.argv[sys.argv.index('--capture-path') + 1])
                    for index, suffix in [(2, ''), (0, '_input'), (1, '_model'), (3, '_graph')]:
                        frame.tabs.SetSelection(index)
                        frame.Refresh()
                        frame.Update()
                        wx.Yield()
                        bitmap = wx.Bitmap(frame.GetSize().width, frame.GetSize().height)
                        dc = wx.MemoryDC(bitmap)
                        pos = frame.GetScreenPosition()
                        dc.Blit(0, 0, bitmap.GetWidth(), bitmap.GetHeight(), wx.ScreenDC(), pos.x, pos.y)
                        dc.SelectObject(wx.NullBitmap)
                        bitmap.SaveFile(str(target.with_name(target.stem + suffix + target.suffix)), wx.BITMAP_TYPE_PNG)
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
