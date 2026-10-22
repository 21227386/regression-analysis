"""Excel input and reusable templates; no filesystem storage of uploaded data."""
from io import BytesIO
import pandas as pd
from openpyxl.worksheet.datavalidation import DataValidation
from model import SHIP_TYPES

EXCEL_HEADERS = {
    '경하중량': '경하 중량(Tonne)', '길이': '길이(m)',
    '폭': '폭(m)', '깊이': '깊이(m)', '순항속력': '순항 속도(knot)',
}


def read_excel(source, sheet_name=0):
    df = pd.read_excel(source, sheet_name=sheet_name, engine='openpyxl')
    df = df.dropna(how='all').reset_index(drop=True)
    aliases = {name.replace(' ', '').casefold(): internal for internal, name in EXCEL_HEADERS.items()}
    aliases.update({f'{name}({unit})': '순항속력'
                    for name in ['순항속력', '순항속도'] for unit in ['kn', 'not', 'knot']})
    aliases['순항속도'] = '순항속력'
    df.columns = [aliases.get(str(col).replace(' ', '').casefold(), str(col).strip()) for col in df.columns]
    if df.columns.duplicated().any():
        raise ValueError('중복된 열 이름을 확인하세요.')
    return df


def workbook_bytes(df):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.rename(columns=EXCEL_HEADERS).to_excel(writer, index=False, sheet_name='실적선')
        ws = writer.sheets['실적선']
        ws.freeze_panes = 'A2'
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 20
        validation = DataValidation(type='list', formula1='"' + ','.join(SHIP_TYPES) + '"')
        validation.errorTitle = '함종 확인'
        validation.error = ', '.join(SHIP_TYPES) + ' 중 선택하세요.'
        validation.showErrorMessage = True
        ws.add_data_validation(validation)
        validation.add('B2:B10000')
    return out.getvalue()
