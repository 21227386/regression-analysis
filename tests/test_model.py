import unittest
import numpy as np
import pandas as pd
from model import example, fit, predict

class RegressionTests(unittest.TestCase):
    def test_recovers_known_equation_and_reference(self):
        df = example()
        factors = df['함종'].map({'호위함': 1., '구축함': 1.25, '고속함': .85, '상륙함': 1.15, '기뢰전함': .9})
        df['경하중량'] = .035*(df['길이']*df['폭']*df['깊이'])**1.05*df['순항속력']**.25*factors
        result = fit(df, '호위함')
        np.testing.assert_allclose([result.k, result.alpha, result.beta], [.035, 1.05, .25], rtol=1e-9)
        np.testing.assert_allclose(result.coefficients['D_T'], [1, .85, 1.25, .9, 1.15], rtol=1e-9)
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
        result = fit(example(), '호위함')
        self.assertGreaterEqual(result.smearing, 1)
        np.testing.assert_allclose(result.results['오차'], result.results['예측중량']-result.results['경하중량'])

if __name__ == '__main__': unittest.main()

class JointTests(unittest.TestCase):
    def test_other_types_contribute_to_common_slopes(self):
        df = example()
        first = fit(df)
        mask = df['함종'] != first.reference
        df.loc[mask, '경하중량'] *= (df.loc[mask, '길이'] / 100) ** 2
        second = fit(df)
        self.assertGreater(abs(second.alpha - first.alpha), .01)
        self.assertEqual(second.coefficients.set_index('함종').loc[second.reference, 'D_T'], 1)

    def test_reference_changes_scale_but_not_predictions_for_noisy_data(self):
        for correction in [False]:
            first = fit(example(), '상륙함', correction)
            for reference in ['호위함', '구축함', '고속함']:
                second = fit(example(), reference, correction)
                np.testing.assert_allclose(first.results['예측중량'], second.results['예측중량'], rtol=1e-10)
                np.testing.assert_allclose([first.alpha, first.beta], [second.alpha, second.beta])
                factors = first.coefficients.set_index('함종')['D_T']
                self.assertAlmostEqual(second.k, first.k * factors[reference])

    def test_landing_many_destroyer_four_frigate_three(self):
        df = example().groupby('함종', group_keys=False).head(3)
        all_rows = example()
        df = pd.concat([all_rows.query("함종 == '상륙함'"),
                        all_rows.query("함종 == '구축함'").head(4),
                        all_rows.query("함종 == '호위함'").head(3)], ignore_index=True)
        result = fit(df)
        self.assertEqual(result.reference, '상륙함')
        self.assertEqual(result.n_parameters, 5)
        self.assertEqual(result.residual_df, 14)
        self.assertTrue(np.isfinite(result.results['예측중량']).all())
        with self.assertRaisesRegex(ValueError, '없는 함종'): predict(result, '고속함', 100, 15, 8, 16)

    def test_single_type_and_single_observation_nonreference_type(self):
        df = example()
        support = df.query("함종 == '상륙함'")
        result = fit(support)
        self.assertEqual(result.n_parameters, 3)
        mixed = fit(pd.concat([support, df.query("함종 == '호위함'").head(1)]))
        self.assertEqual(mixed.n_parameters, 4)
        self.assertAlmostEqual(mixed.results.iloc[-1]['예측중량'], mixed.results.iloc[-1]['경하중량'])

    def test_rank_checks_account_for_type_effects_and_residual_degrees(self):
        df = example()
        # Speed varies overall, but only between types: beta is confounded with D_T.
        df['순항속력'] = df['함종'].map({'호위함': 16, '구축함': 18, '고속함': 20, '상륙함': 14, '기뢰전함': 13})
        with self.assertRaisesRegex(ValueError, '함종 효과'): fit(df)
        df = example().groupby('함종', group_keys=False).head(1)
        with self.assertRaisesRegex(ValueError, '최소 8척'): fit(df)

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

class AvailableTypeTests(unittest.TestCase):
    def test_every_nonempty_type_combination(self):
        from itertools import combinations
        from model import SHIP_TYPES
        data = example()
        for count in range(1, len(SHIP_TYPES) + 1):
            for present in combinations(SHIP_TYPES, count):
                with self.subTest(present=present):
                    result = fit(data[data['함종'].isin(present)])
                    self.assertEqual(set(result.coefficients['함종']), set(present))
                    self.assertEqual(result.n_parameters, count + 2)
                    self.assertEqual(result.reference, present[0])
                    self.assertEqual(result.coefficients.set_index('함종').loc[result.reference, 'D_T'], 1)
                    self.assertTrue(np.isfinite(result.results['예측중량']).all())

    def test_fallback_uses_largest_present_type_and_is_order_independent(self):
        data = example()
        data = data.drop(data.query("함종 == '구축함'").index[:9])
        data = data.drop(data.query("함종 == '호위함'").index[:8])
        data = data.drop(data.query("함종 == '고속함'").index[:6])
        first, shuffled = fit(data), fit(data.sample(frac=1, random_state=1))
        self.assertEqual(first.reference, '상륙함')
        self.assertEqual(shuffled.reference, first.reference)
        np.testing.assert_allclose([first.k, first.alpha, first.beta], [shuffled.k, shuffled.alpha, shuffled.beta])
        fixed = fit(data, reference='호위함')
        np.testing.assert_allclose(first.results['예측중량'], fixed.results['예측중량'])

class MapeObjectiveTests(unittest.TestCase):
    def test_known_global_optimum_with_repeated_dimensions(self):
        # At each identical design, MAPE is minimized at the lower observation,
        # not the geometric mean or the unweighted median.
        base = example().query("함종 == '호위함'").head(6).copy()
        base['경하중량'] = .035 * (base['길이'] * base['폭'] * base['깊이']) ** 1.05 * base['순항속력'] ** .25
        for multipliers in [[1., 10.], [1., 2., 3.]]:
            rows = pd.concat([base.assign(경하중량=base['경하중량'] * factor) for factor in multipliers], ignore_index=True)
            fitted = fit(rows)
            expected = 100 * np.mean([abs(1 / factor - 1) for factor in multipliers])
            self.assertAlmostEqual(fitted.metrics['MAPE (%)'], expected, places=7)
            np.testing.assert_allclose([fitted.k, fitted.alpha, fitted.beta], [.035, 1.05, .25], rtol=1e-6)
            self.assertLess(fitted.metrics['MAPE (%)'], fitted.baseline_mape)

    def test_direct_objective_and_mass_scaling(self):
        data = example()
        first = fit(data)
        self.assertAlmostEqual(first.metrics['MAPE (%)'], first.results['절대오차율(%)'].mean())
        self.assertLessEqual(first.metrics['MAPE (%)'], first.baseline_mape + 1e-8)
        data['경하중량'] *= 100
        scaled = fit(data)
        self.assertAlmostEqual(first.metrics['MAPE (%)'], scaled.metrics['MAPE (%)'], places=7)
        np.testing.assert_allclose(scaled.results['예측중량'], first.results['예측중량'] * 100, rtol=1e-7)
        self.assertEqual(first.smearing, 1)
        with self.assertRaisesRegex(ValueError, 'MAPE 직접 최소화'):
            fit(data, correction=True)
