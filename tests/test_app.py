import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_render_and_predict(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 4)
        self.assertEqual(len(app.get('plotly_chart')), 1)
        app.selectbox(key='surface_type').select('구축함').run()
        app.checkbox[0].check().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('plotly_chart')), 1)
        app.button[-1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 5)
