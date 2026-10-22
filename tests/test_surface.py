import unittest
import numpy as np
from model import example, fit
from surface import mass_surface

class SurfaceTests(unittest.TestCase):
    def test_surface_equation_and_log_plane(self):
        fitted = fit(example(), correction=False)
        factor = fitted.coefficients.set_index('함종').loc['구축함', 'D_T']
        raw = mass_surface(fitted, '구축함')
        plane = mass_surface(fitted, '구축함', True)
        x, y, z = [np.asarray(getattr(raw.data[0], a)) for a in ['x', 'y', 'z']]
        np.testing.assert_allclose(z, fitted.k * factor * fitted.smearing * x**fitted.alpha * y**fitted.beta)
        np.testing.assert_allclose(plane.data[0].z, np.log(z))
        np.testing.assert_allclose(plane.data[0].z, np.log(fitted.k*factor*fitted.smearing) + fitted.alpha*np.asarray(plane.data[0].x) + fitted.beta*np.asarray(plane.data[0].y))
        selected = fitted.results.query("함종 == '구축함'")
        np.testing.assert_allclose(raw.data[1].z, selected['경하중량'])
        np.testing.assert_allclose(raw.data[2].z, selected['예측중량'])
        self.assertEqual(len(raw.data[3].z), len(selected)*3)
        self.assertIn('plotly.js', raw.to_html(include_plotlyjs=True))
