import unittest
import numpy as np
from model import example, fit, predict

class RegressionTests(unittest.TestCase):
    def test_recovers_known_equation_and_reference(self):
        df = example()
        factors = df['함종'].map({'호위함': 1., '구축함': 1.25, '고속함': .85, '지원함': 1.1})
        df['경하중량'] = .035*(df['길이']*df['폭']*df['깊이'])**1.05*df['순항속력']**.25*factors
        result = fit(df, '호위함')
        np.testing.assert_allclose([result.k, result.alpha, result.beta], [.035, 1.05, .25], rtol=1e-9)
        np.testing.assert_allclose(result.coefficients['D_T'], [1, .85, 1.25, 1.1], rtol=1e-9)
        self.assertLess(result.metrics['MAPE (%)'], 1e-9)
        row = df.iloc[0]
        self.assertAlmostEqual(predict(result, row['함종'], *row[['길이','폭','깊이','순항속력']]), row['경하중량'])
        other = fit(df, '구축함')
        np.testing.assert_allclose(other.results['예측중량'], result.results['예측중량'])
        self.assertAlmostEqual(other.k, .035*1.25)

    def test_invalid_and_unidentifiable(self):
        df = example()
        df.loc[0, '길이'] = 0
        with self.assertRaises(ValueError): fit(df, '호위함')
        df = example()
        df['순항속력'] = 20
        with self.assertRaises(ValueError): fit(df, '호위함')
        with self.assertRaises(ValueError): fit(example().head(3), '호위함')

    def test_smearing_and_error_definition(self):
        result = fit(example(), '호위함', True)
        self.assertGreaterEqual(result.smearing, 1)
        np.testing.assert_allclose(result.results['오차'], result.results['예측중량']-result.results['경하중량'])

if __name__ == '__main__': unittest.main()

class SequentialTests(unittest.TestCase):
    def test_other_types_cannot_change_reference_coefficients(self):
        df = example()
        first = fit(df)
        df.loc[df['함종'] == '구축함', '경하중량'] *= 2
        second = fit(df)
        np.testing.assert_allclose([first.k, first.alpha, first.beta], [second.k, second.alpha, second.beta])
        a = first.coefficients.set_index('함종')['D_T']
        b = second.coefficients.set_index('함종')['D_T']
        self.assertAlmostEqual(b['구축함'], 2*a['구축함'])
        self.assertAlmostEqual(b['호위함'], 1)

    def test_dt_is_geometric_mean_ratio_including_correction(self):
        for correction in [False, True]:
            df = example()
            result = fit(df, correction=correction)
            rows = df[df['함종'] == '지원함']
            base = result.smearing*result.k*(rows['길이']*rows['폭']*rows['깊이'])**result.alpha*rows['순항속력']**result.beta
            expected = np.exp(np.log(rows['경하중량']/base).mean())
            self.assertAlmostEqual(result.coefficients.set_index('함종').loc['지원함', 'D_T'], expected)

    def test_more_other_ships_cannot_replace_reference_data(self):
        df = example()
        df = df.drop(df[df['함종'] == '호위함'].index[3:])
        with self.assertRaisesRegex(ValueError, '최소 4척'): fit(df)

class CruiseSpeedTests(unittest.TestCase):
    def test_maximum_speed_is_never_silently_relabelled(self):
        for old in ['최대속력', '최고속력']:
            df = example().rename(columns={'순항속력': old})
            with self.assertRaisesRegex(ValueError, '자동 환산하지 않습니다'): fit(df)

    def test_cruise_speed_is_used_in_prediction(self):
        fitted = fit(example())
        a = predict(fitted, '호위함', 100, 15, 8, 15)
        b = predict(fitted, '호위함', 100, 15, 8, 18)
        self.assertAlmostEqual(b/a, (18/15)**fitted.beta)
