"""Shared desktop workflow: load observations, refit, compare, and estimate."""
from io import BytesIO
import pandas as pd
from model import COLUMNS, fit, predict, validate
from excel_io import workbook_bytes


class EstimatorSession:
    def __init__(self):
        self.data = None
        self.fitted = None
        self.issue = ''

    def load(self, frame, append=False):
        incoming = validate(frame)
        combined = pd.concat([self.data, incoming], ignore_index=True) if append and self.data is not None else incoming
        self.data = combined.reset_index(drop=True)
        self.refit()

    def refit(self):
        # Never leave a previous fit active after observations/settings change.
        self.fitted = None
        self.issue = ''
        if self.data is None:
            self.issue = '실적함 엑셀을 불러오세요.'
            return
        try:
            self.fitted = fit(self.data, correction=False)
        except ValueError as exc:
            self.issue = str(exc)

    def estimate(self, ship_type, length, beam, depth, speed):
        if self.fitted is None:
            raise ValueError(self.issue or '먼저 실적함 자료로 회귀모형을 추정하세요.')
        value = predict(self.fitted, ship_type, length, beam, depth, speed)
        subset = self.data[self.data['함종'] == ship_type]
        values = [length, beam, depth, speed]
        outside = [col for col, item in zip(COLUMNS[3:], values)
                   if item < subset[col].min() or item > subset[col].max()]
        return value, outside

    def input_bytes(self):
        if self.data is None:
            raise ValueError('저장할 입력 자료가 없습니다.')
        return workbook_bytes(self.data)

    def report_bytes(self):
        if self.fitted is None:
            raise ValueError('회귀모형이 아직 추정되지 않았습니다.')
        fit_result = self.fitted
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            self.data.rename(columns={'순항속력': '순항속력 (not)'}).to_excel(writer, sheet_name='입력자료', index=False)
            pd.DataFrame([{'K': fit_result.k, 'alpha': fit_result.alpha, 'beta': fit_result.beta,
                           '기준함종': '호위함', '속력기준': '순항속력 (not)',
                           '추정방식': '호위함 회귀 후 타 함종 DT 산출'}]).to_excel(writer, sheet_name='회귀계수', index=False)
            fit_result.coefficients.to_excel(writer, sheet_name='함종별_DT', index=False)
            fit_result.results.to_excel(writer, sheet_name='실적함_비교', index=False)
            pd.DataFrame([fit_result.metrics]).to_excel(writer, sheet_name='학습자료_적합지표', index=False)
            for sheet in writer.book:
                sheet.freeze_panes = 'A2'
                for col in sheet.columns:
                    sheet.column_dimensions[col[0].column_letter].width = 22
        return out.getvalue()
