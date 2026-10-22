import numpy as np
import pandas as pd
import streamlit as st
from model import COLUMNS, SHIP_TYPES, REFERENCE, example, fit, predict, validate
from excel_io import read_excel, workbook_bytes
from surface import mass_surface

st.set_page_config(page_title='함정 경하중량 회귀분석', layout='wide')
st.title('함정 경하중량 회귀분석')
st.latex(r'W_{LS}=K(LBH)^{\alpha}V_c^{\beta}D_T')
st.caption('표기 not는 knot(노트)와 같은 의미로 사용하며 수치 환산은 하지 않습니다. V_c는 순항속력(not)입니다. 최대속력으로 추정했던 계수는 그대로 재사용하지 않고 순항속력 자료로 다시 학습해야 합니다.')
st.write('단위: 경하중량 tonne · 길이/폭/깊이 m · 순항속력 not. 깊이는 흘수와 구분하여 입력하세요.')
st.info('전체 함종의 자료로 공통 K, α, β와 함종별 D_T를 동시에 추정한 뒤 새 함정 중량을 예측합니다. 지원함 D_T=1입니다.')
with st.expander('순항속력 참고 범위 (사용자 제공 대략값)'):
    st.table(pd.DataFrame({'함종': ['구축함', '호위함', '고속함', '지원함'], '순항속력 (not)': ['17–20', '15–18', '15–20', '12–15']}))
    st.caption('참고 범위이며 자동 환산이나 입력 제한에 사용하지 않습니다. 실적선별 실제 순항속력을 입력하세요.')
file = st.file_uploader('실적선 엑셀 업로드 (.xlsx)', type=['xlsx'])
st.download_button('빈 엑셀 입력 양식 다운로드', workbook_bytes(pd.DataFrame(columns=COLUMNS)),
                   'ship_template.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
st.download_button('가상 예제 엑셀 다운로드', workbook_bytes(example()),
                   'synthetic_example.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
if file:
    try:
        with pd.ExcelFile(file, engine='openpyxl') as book:
            sheet = st.selectbox('자료 시트', book.sheet_names)
            source = read_excel(book, sheet)
    except Exception as exc:
        st.error(f'엑셀을 읽을 수 없습니다: {exc}')
        st.stop()
else:
    st.warning('현재 표시된 자료는 기능 확인용 가상 자료입니다. 실제 함정의 계수나 성능을 나타내지 않습니다.')
    source = example()
st.caption('첫 행은 열 이름이어야 합니다. 필수 열: ' + ', '.join(COLUMNS[1:]) + '. 함명은 선택 항목입니다. 함종: 구축함/호위함/고속함/지원함.')
st.caption('단위: 경하중량 tonne, 길이·폭·깊이 m, 순항속력 not. 빈 행은 제외합니다.')
st.caption('자료가 늘어나면 기존 실적선과 새 실적선을 합친 엑셀을 업로드하거나 아래 표에 행을 추가하세요. 매번 전체 입력 자료로 다시 학습합니다. 중복 행은 의도치 않은 가중치가 되므로 제거하세요.')
edited = st.data_editor(source, num_rows='dynamic', width='stretch',
                        column_config={'함종': st.column_config.SelectboxColumn(options=SHIP_TYPES, required=True),
                                       '순항속력': st.column_config.NumberColumn('순항속력 (not)', min_value=0.01, required=True)})
try:
    data = validate(edited)
    st.download_button('현재 학습자료 엑셀 저장', workbook_bytes(data), 'training_data.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reference = REFERENCE
    absent = [t for t in SHIP_TYPES if t not in data['함종'].unique()]
    if absent:
        st.warning('자료가 없어 설계계수를 추정할 수 없는 함종: ' + ', '.join(absent))
    correction = st.checkbox('로그 역변환 편향 보정 적용 (Duan smearing)', value=False,
                             help='전체 자료의 잔차로 보정배율 S를 추정합니다. 최종 식은 S·K·(LBH)^α·V^β·D_T입니다.')
    fitted = fit(data, reference, correction)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
st.subheader('산출 계수')
st.caption('전체 함종의 자료로 K, α, β와 함종별 D_T를 동시에 추정합니다. 지원함 D_T는 1로 유지합니다.')
st.dataframe(pd.DataFrame({'K': [fitted.k], 'α': [fitted.alpha], 'β': [fitted.beta], '보정배율 S': [fitted.smearing]}), hide_index=True)
st.dataframe(fitted.coefficients, hide_index=True)
if fitted.condition > 30:
    st.warning(f'변수 간 공선성이 높습니다 (표준화 설계행렬 조건수 {fitted.condition:.1f}). 계수가 불안정할 수 있습니다.')
if (fitted.coefficients['실적선 수'] < 5).any():
    st.warning('일부 함종의 자료가 5척 미만입니다. 해당 설계계수의 신뢰성이 낮을 수 있습니다.')
st.caption('전체 함종 로그 선형 최소제곱: ln(W) = ln(K) + α ln(LBH) + β ln(V) + ln(D_T). K는 입력 단위계에 의존합니다.')
st.subheader('실적선 비교')
st.caption('자료 수 증가만으로 정확도 향상이 보장되지는 않습니다. 어느 함종이든 자료를 업데이트하면 공통 회귀계수와 함종별 D_T를 함께 다시 추정합니다. 서버에 학습자료를 자동 보관하지 않으므로 현재 학습자료 엑셀을 저장해 두세요.')
st.warning('아래 수치는 학습에 사용한 실적선의 적합 오차입니다. 새로운 함정에 대한 예측 정확도를 보장하지 않습니다.')
cols = st.columns(4)
for col, (name, val) in zip(cols, fitted.metrics.items()):
    col.metric(name, f'{val:.4g}')
st.caption('오차 = 예측 − 실적. 양수는 과대 추정, 음수는 과소 추정입니다.')
st.dataframe(fitted.results, hide_index=True, width='stretch')
st.scatter_chart(fitted.results, x='경하중량', y='예측중량', color='함종')
st.caption('가로축: 실적 경하중량, 세로축: 예측 경하중량 (tonne). 두 값이 같을수록 잘 맞습니다.')
st.download_button('실적선 비교 CSV', fitted.results.to_csv(index=False).encode('utf-8-sig'), 'fit_results.csv', 'text/csv')
export = fitted.coefficients.assign(K=fitted.k, alpha=fitted.alpha, beta=fitted.beta, S=fitted.smearing, 기준함종=reference, 속력기준='순항속력(not)')
st.download_button('계수 CSV', export.to_csv(index=False).encode('utf-8-sig'), 'coefficients.csv', 'text/csv')
st.subheader('함종별 3차원 경하중량 곡면')
st.caption('함종의 D_T를 고정하고 LBH와 순항속력에 따른 예측 중량을 표시합니다. 마우스로 회전·확대할 수 있습니다.')
surface_type = st.selectbox('곡면에 표시할 함종', fitted.coefficients['함종'], key='surface_type')
log_surface = st.checkbox('로그 공간 평면으로 보기', help='ln(W) = ln(K·D_T·S) + α ln(LBH) + β ln(V)이므로 로그 공간에서는 평면입니다.')
st.caption('빨간 점은 실적 중량, 파란 점은 같은 치수·속력의 예측 중량이며 연결선은 두 값의 차이입니다. 곡면은 선택 함종의 관측 최소·최대 범위를 사용하지만, 자료가 드문 조합에서도 표시되므로 주의하세요.')
try:
    surface_fig = mass_surface(fitted, surface_type, log_surface)
    st.plotly_chart(surface_fig, width='stretch', key='mass_surface')
    st.download_button('3차원 그래프 HTML 다운로드', surface_fig.to_html(include_plotlyjs=True).encode('utf-8'),
                       'mass_surface.html', 'text/html')
except ValueError as exc:
    st.error(str(exc))
st.subheader('새 함정 경하중량 추정')
with st.form('prediction'):
    typ = st.selectbox('함종', fitted.coefficients['함종'])
    fields = st.columns(4)
    vals = [col.number_input(label, min_value=0.01, value=float(data[key].median()))
            for col, label, key in zip(fields, ['길이 (m)', '폭 (m)', '깊이 (m)', '순항속력 (not)'], ['길이', '폭', '깊이', '순항속력'])]
    submitted = st.form_submit_button('추정')
if submitted:
    try:
        st.metric('예측 경하중량', f'{predict(fitted, typ, *vals):,.2f} tonne')
        subset = data[data['함종'] == typ]
        if any(value < subset[key].min() or value > subset[key].max() for value, key in zip(vals, ['길이', '폭', '깊이', '순항속력'])):
            st.warning('선택 함종의 학습 자료 범위를 벗어난 입력이 있습니다. 외삽 결과는 신중하게 사용하세요.')
    except ValueError as exc:
        st.error(str(exc))
