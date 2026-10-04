"""Synthetic edge cases; these tests never connect to the database."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest

from run_analysis import build_pairs, canonicalize, cluster_interval, summarize, near_far_comparison


def row(number, stamp, target=date(2024, 1, 10), value='20'):
    return dict(forecast_issue_id=number, source_file_id=number,
                bulletin_time_hkt=datetime.fromisoformat(stamp), valid_date=target,
                lead_days=(target - datetime.fromisoformat(stamp).date()).days,
                forecast_tmin_c=None if value is None else Decimal(value),
                forecast_tmax_c=Decimal('25'), forecast_rh_min_pct=Decimal('60'),
                forecast_rh_max_pct=Decimal('90'), psr='Low', wind='East', weather='Fine')


class RevisionTests(unittest.TestCase):
    def test_identical_duplicate_collapsed(self):
        clean, audit = canonicalize([row(2, '2024-01-02 11:30'), row(1, '2024-01-02 11:30')])
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]['forecast_issue_id'], 1)
        self.assertEqual(audit[0]['removed_rows'], 1)

    def test_conflicting_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            canonicalize([row(1, '2024-01-02 11:30'), row(2, '2024-01-02 11:30', value='21')])

    def test_distinct_times_preserved(self):
        clean, _ = canonicalize([row(1, '2024-01-02 11:30'), row(2, '2024-01-02 16:30')])
        self.assertEqual(len(clean), 2)

    def test_sign_and_exact_decimal_change(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30', value='20.1'), row(2, '2024-01-02 16:30', value='20.3')])
        self.assertEqual(pairs[0]['tmin'], Decimal('0.2'))
        self.assertEqual(pairs[0]['elapsed_hours'], 5)

    def test_zero_is_in_denominator(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30'), row(2, '2024-01-02 16:30'), row(3, '2024-01-03 11:30', value='22')])
        result = next(r for r in summarize(pairs, intervals=False) if r['scope'] == 'consecutive_le24h' and r['metric'] == 'tmin')
        self.assertEqual(result['n_pairs'], 2)
        self.assertEqual(result['mean_absolute_revision'], 1)
        self.assertEqual(result['revision_frequency_pct'], 50)

    def test_null_does_not_bridge(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30'), row(2, '2024-01-02 16:30', value=None), row(3, '2024-01-03 11:30', value='22')])
        self.assertTrue(all(p['tmin'] is None for p in pairs))

    def test_long_gap_not_in_primary(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30'), row(2, '2024-01-04 16:30')])
        self.assertEqual([p['scope'] for p in pairs], ['all_archived_pairs'])

    def test_lead_zero_excluded(self):
        pairs = build_pairs([row(1, '2024-01-09 16:30'), row(2, '2024-01-10 00:00')])
        self.assertEqual(pairs, [])

    def test_lead_ten_excluded(self):
        self.assertEqual(build_pairs([row(1, '2023-12-31 16:30'), row(2, '2024-01-01 16:30')]), [])

    def test_daily_latest_not_every_bulletin(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30', value='20'), row(2, '2024-01-02 16:30', value='21'), row(3, '2024-01-03 11:30', value='23')])
        daily = [p for p in pairs if p['scope'] == 'daily_latest']
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0]['tmin'], Decimal('2'))

    def test_missing_target_in_intermediate_bulletin_flagged(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30'), row(2, '2024-01-02 16:30', target=date(2024, 1, 11)), row(3, '2024-01-03 07:50')])
        self.assertFalse(any(p['scope'] == 'consecutive_le24h' for p in pairs))
        self.assertEqual(pairs[0]['skipped_archived_bulletins'], 1)

    def test_target_dates_not_mixed(self):
        pairs = build_pairs([row(1, '2024-01-02 11:30'), row(2, '2024-01-03 11:30', target=date(2024, 1, 11))])
        self.assertEqual(pairs, [])

    def test_psr_category_no_numeric_conversion(self):
        a, b = row(1, '2024-01-02 11:30'), row(2, '2024-01-02 16:30')
        b['psr'] = 'High'
        self.assertTrue(build_pairs([a, b])[0]['psr_changed'])

    def test_bootstrap_deterministic_and_constant(self):
        days = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 2)]
        self.assertEqual(cluster_interval([2, 2, 2], days, 100, 42), (2, 2))
        self.assertEqual(cluster_interval([1, 2, 3], days, 100, 42), cluster_interval([1, 2, 3], days, 100, 42))

    def test_single_cluster_has_no_interval(self):
        self.assertEqual(cluster_interval([1, 2], [date(2024, 1, 1)] * 2, 100, 42), (None, None))

    def test_near_far_equal_target_weights_and_excludes_lead_nine(self):
        def pair(target, lead, value):
            return dict(scope='consecutive_le24h', valid_date=target, lead_days=lead,
                        tmin=Decimal(value), tmax=None, rh_min=None, rh_max=None)
        a, b = date(2024, 1, 10), date(2024, 1, 11)
        pairs = [pair(a, 1, '0'), pair(a, 2, '2'), pair(a, 7, '3'),
                 pair(a, 9, '100'), pair(b, 1, '4'), pair(b, 8, '2')]
        result = near_far_comparison(pairs, 100, 42)[0]
        self.assertEqual(result['n_matched_target_dates'], 2)
        self.assertEqual(result['mean_near_target_mar'], 2.5)
        self.assertEqual(result['mean_far_target_mar'], 2.5)
        self.assertEqual(result['near_minus_far'], 0)

    def test_near_far_requires_both_windows_for_each_target(self):
        pairs = [dict(scope='consecutive_le24h', valid_date=date(2024, 1, 10),
                      lead_days=1, tmin=Decimal('1'), tmax=None, rh_min=None, rh_max=None)]
        self.assertEqual(near_far_comparison(pairs, 100, 42), [])


if __name__ == '__main__':
    unittest.main()
