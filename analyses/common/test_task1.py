"""Synthetic method checks; deliberately separate from live-data verification."""
from datetime import date, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.task1 import FOLDERS, interval, metric_summary, revision_pairs, daily_latest, season
from common.rh_observations import validate_reports, number


def load(rq):
    spec = importlib.util.spec_from_file_location(f'test_rq{rq}',Path(__file__).resolve().parents[1]/FOLDERS[rq]/'run_analysis.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rq2,rq3,rq4,rq6,rq7 = (load(r) for r in (2,3,4,6,7))


def row(i,dt,target=date(2024,1,10),value=20):
    return dict(forecast_issue_id=i,bulletin_time_hkt=dt,valid_date=target,
                lead_days=(target-dt.date()).days,forecast_tmin_c=value)


class Methods(unittest.TestCase):
    def rh_report(self,**changes):
        target=date(2022,1,1)
        return dict(report_date=target,source_observation_date='20220101',observed_rh_min_text='50',observed_rh_max_text='80',
                    bulletin_date=target+timedelta(days=1),bulletin_time='0015') | changes

    def test_rh_observation_date_not_publication_date(self):
        values,audit=validate_reports([self.rh_report()],date(2022,1,1),date(2022,1,3))
        self.assertEqual(values['rh_min'],{date(2022,1,1):50})
        self.assertEqual(audit['n_missing_or_rejected_dates'],1)

    def test_rh_reject_source_date_mismatch(self):
        values,audit=validate_reports([self.rh_report(source_observation_date='20220102')],date(2022,1,1),date(2022,1,2))
        self.assertEqual(values['rh_min'],{})
        self.assertEqual(audit['rejected_by_reason'],{'source_date_disagrees':1})

    def test_rh_no_missing_to_zero(self):
        self.assertIsNone(number(''))
        self.assertIsNone(number('Trace'))
        self.assertIsNone(number('NaN'))
        self.assertEqual(number('0'),0)

    def test_rh_invalid_endpoints_excluded(self):
        for changes in [dict(observed_rh_min_text='101'),dict(observed_rh_min_text='90'),dict(observed_rh_max_text='M')]:
            values,audit=validate_reports([self.rh_report(**changes)],date(2022,1,1),date(2022,1,2))
            self.assertEqual(audit['n_valid_dates'],0)
            self.assertEqual(values['rh_max'],{})

    def test_rh_duplicate_dates_require_review(self):
        with self.assertRaises(ValueError):
            validate_reports([self.rh_report(),self.rh_report()],date(2022,1,1),date(2022,1,2))

    def test_rh_climatology_training_frozen_2022(self):
        observed={date(2022,1,1)+timedelta(days=i):70. for i in range(365)}
        baseline,n=rq4.fit_rh_climatology(observed)
        observed[date(2023,1,1)]=1e9
        self.assertEqual(rq4.fit_rh_climatology(observed),(baseline,n))
        self.assertEqual(n,365)

    def test_ffi_monotone(self):
        self.assertEqual(rq2.flip_flop_index([1,2,3,4]),0)

    def test_ffi_constant(self):
        self.assertEqual(rq2.flip_flop_index([1,1,1]),0)

    def test_ffi_short(self):
        self.assertIsNone(rq2.flip_flop_index([1,2]))

    def test_ffi_example(self):
        self.assertEqual(rq2.flip_flop_index([50,20,40,80]),15)

    def test_ffi_reversal(self):
        self.assertEqual(rq2.flip_flop_index([1,3,1]),2)

    def test_gap_breaks_segments(self):
        rows = [row(i,datetime(2024,1,d),value=v) for i,d,v in ((1,2,20),(2,3,21),(3,6,20))]
        self.assertEqual([len(p) for _,p in rq2.segments(rows,'consecutive_le24h','forecast_tmin_c')],[2,1])

    def test_null_breaks_segments(self):
        rows = [row(i,datetime(2024,1,i+1),value=v) for i,v in ((1,20),(2,None),(3,21))]
        self.assertEqual([len(p) for _,p in rq2.segments(rows,'daily_latest','forecast_tmin_c')],[1,1])

    def test_no_bridge_global_missing_bulletin(self):
        rows = [row(1,datetime(2024,1,2)),row(2,datetime(2024,1,2,6),date(2024,1,9)),row(3,datetime(2024,1,2,12))]
        self.assertEqual(revision_pairs(rows),[])

    def test_daily_latest_target_specific(self):
        rows = [row(1,datetime(2024,1,2)),row(2,datetime(2024,1,2,12)),row(3,datetime(2024,1,2,18),date(2024,1,9))]
        self.assertEqual({r['forecast_issue_id'] for r in daily_latest(rows)},{2,3})

    def test_lead_zero_excluded(self):
        self.assertEqual(revision_pairs([row(1,datetime(2024,1,9)),row(2,datetime(2024,1,10))],'daily_latest'),[])

    def test_lead_ten_excluded(self):
        self.assertEqual(revision_pairs([row(1,datetime(2023,12,31)),row(2,datetime(2024,1,1))],'daily_latest'),[])

    def test_improved(self):
        self.assertEqual(rq3.classify_improvement(10,11,12),('improved',1.))

    def test_worsened(self):
        self.assertEqual(rq3.classify_improvement(11,10,12),('worsened',-1.))

    def test_changed_but_tied(self):
        self.assertEqual(rq3.classify_improvement(10,14,12),('tied',0.))

    def test_unchanged_tied(self):
        self.assertEqual(rq3.classify_improvement(10,10,12),('tied',0.))

    def test_error_units(self):
        s=metric_summary([1,-1,3]);self.assertAlmostEqual(s['mae'],5/3);self.assertEqual(s['bias'],1)
        self.assertAlmostEqual(s['rmse'],np.sqrt(11/3))

    def test_empty_score(self):
        self.assertEqual(metric_summary([])['mae'],None)

    def test_calendar_alignment(self):
        self.assertEqual(rq4.calendar_index(date(2022,3,1)),rq4.calendar_index(date(2024,3,1)))
        self.assertEqual(rq4.calendar_index(date(2024,2,29)),59)

    def test_climatology_no_study_leakage(self):
        observed={date(1991,1,1)+timedelta(days=i):10. for i in range(10958)}
        a,_=rq4.fit_climatology(observed)
        observed[date(2022,1,1)]=100000
        b,_=rq4.fit_climatology(observed)
        self.assertEqual(a,b)

    def test_rh_not_extrema(self):
        self.assertEqual(rq4.rh_distance(70,50,80),0)
        self.assertEqual(rq4.rh_distance(90,50,80),10)
        self.assertEqual(rq4.rh_distance(40,50,80),10)

    def test_rain_trace_not_zero_amount(self):
        self.assertEqual(rq6.rainfall_interval(dict(data_completeness='C',value_numeric=None,value_text='Trace')),(0,.05))

    def test_incomplete_rain_excluded(self):
        self.assertIsNone(rq6.rainfall_interval(dict(data_completeness='I',value_numeric=20,value_text='20')))

    def test_negative_rain_rejected(self):
        with self.assertRaises(ValueError):
            rq6.rainfall_interval(dict(data_completeness='C',value_numeric=-1,value_text='-1'))

    def test_brier_bounds_contain_midpoint(self):
        for category,(lo,hi) in rq6.PSR_BANDS.items():
            for event in (0,1):
                a,b=rq6.brier_bounds(category,event);score=((lo+hi)/2-event)**2
                self.assertLessEqual(a,score);self.assertGreaterEqual(b,score)

    def test_alarm_denominators(self):
        c=rq6.confusion([1,1,0,0,0],[1,0,1,0,0])
        self.assertEqual((c['tp'],c['fp'],c['fn'],c['tn']),(1,1,1,2))
        self.assertEqual(c['hit_rate'],.5);self.assertEqual(c['false_alarm_ratio'],.5)
        self.assertAlmostEqual(c['false_positive_rate'],1/3)

    def test_empty_alarm_denominators(self):
        c=rq6.confusion([0,0],[0,0]);self.assertIsNone(c['hit_rate']);self.assertIsNone(c['false_alarm_ratio'])

    def test_seasons(self):
        self.assertEqual([season(date(2024,m,1)) for m in (1,3,6,9,12)],['DJF','MAM','JJA','SON','DJF'])

    def test_regime_hierarchy(self):
        self.assertEqual(rq7.regime('Monsoon and tropical cyclone with a trough.'),'cyclone_mention')
        self.assertEqual(rq7.regime('A trough and monsoon'),'trough_mention')
        self.assertEqual(rq7.regime('monsoonal cloud'),'other')
        self.assertEqual(rq7.regime(None),'missing')

    def test_linear_shap_additivity(self):
        x=np.array([[1.,2.,4.],[1.,1.,0.]])
        beta=np.array([5.,2.,-1.]);phi,base=rq7.linear_shap(x,beta,np.array([1.,0.,3.]))
        np.testing.assert_allclose(phi,[[0,4,-1],[0,2,3]])
        np.testing.assert_allclose(base+phi.sum(axis=1),x@beta)

    def test_ols_known_coefficients(self):
        x=np.column_stack((np.ones(100),np.arange(100)))
        y=3+2*x[:,1]
        beta,_,g=rq7.fit_cluster_ols(x,y,[date(2022,1,1)+timedelta(days=i) for i in range(100)])
        np.testing.assert_allclose(beta,[3,2],atol=1e-10);self.assertEqual(g,15)

    def test_stratified_known_contrast(self):
        rows=[dict(valid_date=date(2022,1,1)+timedelta(days=i),lead_days=1,season='DJF',
                   factor=i%2,outcome=2+3*(i%2)) for i in range(100)]
        c=rq7.stratified_contrast(rows,'factor',1,0,('lead_days','season'))
        self.assertAlmostEqual(c['mean_difference_c'],3)
        self.assertAlmostEqual(c['ci95_low'],3);self.assertAlmostEqual(c['ci95_high'],3)

    def test_no_common_support(self):
        rows=[dict(valid_date=date(2022,1,1),lead_days=1,factor=0,outcome=2)]
        self.assertIsNone(rq7.stratified_contrast(rows,'factor',1,0,('lead_days',))['mean_difference_c'])

    def test_bootstrap_date_cluster_deterministic(self):
        dates=[date(2022,1,1),date(2022,1,1),date(2022,1,2)]
        self.assertEqual(interval([1,3,4],dates),interval([1,3,4],dates))


if __name__=='__main__':
    unittest.main()
