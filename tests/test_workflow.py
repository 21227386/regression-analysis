from io import BytesIO
import unittest
import pandas as pd
import numpy as np
from model import SHIP_TYPES, example
from excel_io import read_excel
from workflow import EstimatorSession

class WorkflowTests(unittest.TestCase):
    def test_upload_estimate_append_export(self):
        session = EstimatorSession()
        session.load(example())
        value, outside = session.estimate('호위함', 100, 15, 8, 16)
        self.assertTrue(np.isfinite(value) and value > 0)
        first_k = session.fitted.k
        addition = example().query("함종 == '구축함'").iloc[:2].copy()
        addition['경하중량'] *= 2
        session.load(addition, append=True)
        self.assertEqual(len(session.data), len(example()) + 2)
        self.assertNotAlmostEqual(session.fitted.k, first_k)
        loaded = read_excel(BytesIO(session.input_bytes()))
        self.assertEqual(len(loaded), len(example()) + 2)
        book = pd.ExcelFile(BytesIO(session.report_bytes()))
        self.assertEqual(len(book.sheet_names), 5)
        self.assertEqual(len(pd.read_excel(book, sheet_name='실적함_비교')), len(example()) + 2)

    def test_insufficient_replacement_clears_previous_model(self):
        session = EstimatorSession()
        session.load(example())
        self.assertIsNotNone(session.fitted)
        session.load(example().head(2))
        self.assertIsNone(session.fitted)
        with self.assertRaises(ValueError): session.estimate('호위함', 100, 15, 8, 16)

    def test_invalid_file_leaves_loaded_dataset_unchanged(self):
        session = EstimatorSession()
        session.load(example())
        previous = session.fitted
        invalid = example()
        invalid.loc[0, '순항속력'] = 0
        with self.assertRaises(ValueError): session.load(invalid)
        self.assertIs(session.fitted, previous)
        self.assertEqual(len(session.data), len(example()))

class UncorrectedWorkflowTests(unittest.TestCase):
    def test_no_bias_option_or_exported_s_and_base_equation(self):
        session = EstimatorSession()
        self.assertFalse(hasattr(session, 'correction'))
        session.load(example())
        fitted = session.fitted
        self.assertEqual(fitted.smearing, 1)
        expected = fitted.k*(100*15*8)**fitted.alpha*16**fitted.beta
        value, _ = session.estimate(fitted.reference, 100, 15, 8, 16)
        self.assertAlmostEqual(value, expected)
        coefficients = pd.read_excel(BytesIO(session.report_bytes()), sheet_name='회귀계수')
        self.assertNotIn('S', coefficients.columns)
        self.assertEqual(coefficients.loc[0, '기준함종'], fitted.reference)
        self.assertIn('동시 추정', coefficients.loc[0, '추정방식'])
        self.assertIn('MAPE 직접 최소화', coefficients.loc[0, '추정방식'])
        self.assertEqual(coefficients.loc[0, '최적화 기준'], 'MAPE (%)')

    def test_comparison_scope_and_undefined_r_squared(self):
        session = EstimatorSession()
        session.load(example())
        fitted = session.fitted
        all_rows, metrics = session.comparison()
        self.assertEqual(len(all_rows), len(example()))
        self.assertAlmostEqual(metrics['MAE'], fitted.metrics['MAE (tonne)'])
        for kind in SHIP_TYPES:
            rows, values = session.comparison(kind)
            self.assertEqual(len(rows), 12)
            self.assertEqual(set(rows['함종']), {kind})
            self.assertAlmostEqual(values['MAPE'], rows['오차율(%)'].abs().mean())
        self.assertIs(session.fitted, fitted)
        session.load(example().query("함종 == '상륙함'"))
        self.assertEqual(session.comparison('호위함')[1], {})
        session.fitted.results = session.fitted.results.iloc[:1]
        self.assertTrue(np.isnan(session.comparison()[1]['R²']))

    def test_landing_ship_prediction_and_exported_units(self):
        session = EstimatorSession()
        session.load(example())
        prediction, _ = session.estimate('상륙함', 100, 15, 8, 16)
        self.assertGreater(prediction, 0)
        rows, metrics = session.comparison('상륙함')
        self.assertEqual(len(rows), 12)
        self.assertTrue(np.isfinite(metrics['MAE']))
        book = pd.ExcelFile(BytesIO(session.report_bytes()))
        self.assertIn('순항 속도(knot)', pd.read_excel(book, sheet_name='입력자료').columns)
        self.assertIn('상륙함', pd.read_excel(book, sheet_name='함종별_DT')['함종'].tolist())
        self.assertIn('상륙함', pd.read_excel(book, sheet_name='학습자료_적합지표')['조회 범위'].tolist())
        self.assertEqual(pd.read_excel(book, sheet_name='회귀계수').loc[0, '속력기준'], '순항속력 (kn)')

    def test_absent_types_excluded_from_report_and_cannot_be_predicted(self):
        session = EstimatorSession()
        session.load(example().query("함종 == '상륙함'"))
        self.assertEqual(session.fitted.reference, '상륙함')
        self.assertGreater(session.estimate('상륙함', 100, 15, 8, 16)[0], 0)
        with self.assertRaisesRegex(ValueError, '없는 함종'):
            session.estimate('지원함', 100, 15, 8, 16)
        book = pd.ExcelFile(BytesIO(session.report_bytes()))
        self.assertEqual(pd.read_excel(book, sheet_name='함종별_DT')['함종'].tolist(), ['상륙함'])
        self.assertEqual(pd.read_excel(book, sheet_name='학습자료_적합지표')['조회 범위'].tolist(), ['전체 함종', '상륙함'])
        self.assertEqual(pd.read_excel(book, sheet_name='회귀계수').loc[0, '기준함종'], '상륙함')

    def test_mine_warfare_ship_prediction_and_report(self):
        session = EstimatorSession()
        session.load(example().query("함종 == '기뢰전함'"))
        self.assertEqual(session.fitted.reference, '기뢰전함')
        self.assertGreater(session.estimate('기뢰전함', 100, 15, 8, 16)[0], 0)
        self.assertEqual(len(session.comparison('기뢰전함')[0]), 12)
        book = pd.ExcelFile(BytesIO(session.report_bytes()))
        self.assertEqual(pd.read_excel(book, sheet_name='함종별_DT')['함종'].tolist(), ['기뢰전함'])
        self.assertEqual(pd.read_excel(book, sheet_name='학습자료_적합지표')['조회 범위'].tolist(), ['전체 함종', '기뢰전함'])
