import unittest
import numpy as np
from run_analysis import metrics,equal_station_metrics

class Methods(unittest.TestCase):
    def test_unequal_coverage_does_not_reweight_stations(self):
        e=np.array([[0,6],[0,np.nan],[0,np.nan]])
        self.assertEqual(equal_station_metrics(e)['mae'],3)
        self.assertEqual(metrics(e)['mae'],1.5)
    def test_group_rmse_is_root_mean_station_mse(self):
        e=np.array([[0,4],[0,4]])
        self.assertAlmostEqual(equal_station_metrics(e)['rmse'],np.sqrt(8))
    def test_missing_is_not_zero(self):
        self.assertEqual(metrics([np.nan,4])['mae'],4)
        self.assertEqual(metrics([np.nan,4])['n'],1)
    def test_bias_decomposition_not_mae_subtraction(self):
        forecast=np.array([20,16]);hko=np.array([20,20]);station=np.array([16,16])
        np.testing.assert_allclose(forecast-station,(forecast-hko)+(hko-station))
        self.assertNotEqual(metrics(forecast-station)['mae'],metrics(forecast-hko)['mae']+metrics(hko-station)['mae'])
    def test_zero_coverage_station_rejected(self):
        with self.assertRaises(ValueError):equal_station_metrics(np.array([[2,np.nan]]))

if __name__=='__main__':unittest.main()
