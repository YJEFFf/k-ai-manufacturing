"""Regression and numerical tests for the bounded revision."""
import unittest
from datetime import datetime, timezone

import numpy as np

from core import HERE, Detector, features, load_records, save_json, sha, split_records
from revise import PooledLength, RevisedDetector


class RevisionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rs,_=load_records()
        roles=split_records(rs,"P1")
        cls.fit=features(roles["fit"])
        cls.evaluation=features(roles["evaluation"])

    def test_baseline_is_unchanged(self):
        np.testing.assert_array_equal(Detector("B1").fit(self.fit).score(self.evaluation),
                                      RevisedDetector("B1").fit(self.fit).score(self.evaluation))

    def test_shrinkage_is_not_local_variance_collapse(self):
        x=np.r_[np.arange(60),np.linspace(40,40.01,10)]
        n=np.r_[np.full(60,50),np.full(10,10)]
        scaler=PooledLength().fit(x,n)
        for (lo,hi),(center,scale) in scaler.by_length.items():
            count=((n>=lo)&(n<=hi)).sum()
            w=count/(count+30)
            self.assertGreaterEqual(scale**2+1e-10,(1-w)*scaler.global_stats[1]**2)

    def test_single_point_local_uses_global(self):
        scaler=PooledLength().fit(np.r_[np.arange(60),1000],np.r_[np.full(60,50),1])
        self.assertNotIn((1,9),scaler.by_length)

    def test_selective_condition_changes_only_lower_channel(self):
        s0=RevisedDetector("S0_global_B1").fit(self.fit).score(self.evaluation,diagnostic=True)
        s1=RevisedDetector("S1_global_C1").fit(self.fit).score(self.evaluation,diagnostic=True)
        s2=RevisedDetector("S2_lower_C1").fit(self.fit).score(self.evaluation,diagnostic=True)
        np.testing.assert_allclose(s2["components"][:,0],s0["components"][:,0],equal_nan=True)
        np.testing.assert_allclose(s2["components"][:,1:],s1["components"][:,1:],equal_nan=True)

    def test_knn_keeps_current_and_no_self_neighbor(self):
        model=RevisedDetector("S5_vibration_knn_current").fit(self.fit)
        s0=RevisedDetector("S0_global_B1").fit(self.fit).score(self.evaluation,diagnostic=True)
        trace=model.score(self.evaluation,diagnostic=True)
        np.testing.assert_allclose(trace["components"][:,2:],s0["components"][:,2:],equal_nan=True)
        loo=model.score(self.fit)
        self.assertTrue(np.isfinite(loo).all())
        self.assertTrue(np.all(loo>0))
        self.assertGreater(model.distance_multiplier,0)

    def test_knn_foreign_parent_namespace(self):
        model=RevisedDetector("S5_vibration_knn_current").fit(self.fit)
        a=self.fit.iloc[[0]].copy()
        b=a.copy()
        a["parent_key"]="external:0"
        b["parent_key"]="external:100000"
        b["parent"]=100000
        np.testing.assert_array_equal(model.score(a),model.score(b))


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RevisionContracts))
    save_json(HERE/"evidence/revision_contracts.json",dict(
        tested_utc=datetime.now(timezone.utc).isoformat(),tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),successful=result.wasSuccessful(),
        code_sha256={p.name:sha(p) for p in sorted(HERE.glob("*.py"))}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
