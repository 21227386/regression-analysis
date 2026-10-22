from io import BytesIO
import unittest
import pandas as pd
import numpy as np
from model import example
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
        self.assertEqual(len(session.data), 50)
        self.assertEqual(session.fitted.k, first_k)
        loaded = read_excel(BytesIO(session.input_bytes()))
        self.assertEqual(len(loaded), 50)
        book = pd.ExcelFile(BytesIO(session.report_bytes()))
        self.assertEqual(len(book.sheet_names), 5)
        self.assertEqual(len(pd.read_excel(book, sheet_name='실적함_비교')), 50)

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
        self.assertEqual(len(session.data), 48)
