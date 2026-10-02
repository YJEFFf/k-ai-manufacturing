"""Tests for data leakage, information time, numerical contracts and injections."""
from dataclasses import replace
import copy
import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from core import (HERE, BINS, COLS, Detector, Generator, RankCalibration, Record,
                  RobustLength, features, fit_suite, load_records, records_from_frame,
                  save_json, sha, sine_basis, split_records)


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.contract = load_records()
        cls.roles = split_records(cls.records, "P0")
        cls.fit = features(cls.roles["fit"])
        cls.cal = features(cls.roles["cal"])
        cls.model = Detector("C1d1").fit(cls.fit)
        cls.generator = Generator(cls.fit, "P0")

    def test_source_conservation(self):
        self.assertEqual(self.contract["original_rows"], 20000)
        self.assertEqual(self.contract["retained_rows"], 19999)
        self.assertEqual(self.contract["source_mapping_rows"], 20000)
        self.assertEqual(self.contract["records"], 599)
        self.assertEqual(self.contract["duplicate_rows"], [11565])
        self.assertEqual(sorted(i for r in self.records for i in r.source_rows), list(range(20000)))

    def test_fold_counts_and_parent_separation(self):
        for fold, counts in [("P0", [81,77,157]), ("P1", [158,157,156]), ("P2", [316,156,126])]:
            roles = split_records(self.records, fold)
            self.assertEqual([len(v) for v in roles.values()], counts)
            ids = [r.parent for values in roles.values() for r in values]
            self.assertEqual(len(ids), len(set(ids)))

    def test_logged_decision_time_including_eof(self):
        for i, r in enumerate(self.records):
            self.assertGreater(r.decision_m, r.end_m)
            self.assertLessEqual(r.decision_m, r.end_m+0.5/60+1e-10)
            if i+1 < len(self.records):
                self.assertLessEqual(r.decision_m, self.records[i+1].start_m+1e-10)
        self.assertAlmostEqual(self.records[-1].decision_m-self.records[-1].end_m, .5/60)

    def test_boundary_inclusive_and_quality_rejection(self):
        base = pd.Timestamp("2026-01-01")
        ns = np.array([0,80_000_000,200_000_000,320_000_001])
        raw = pd.DataFrame({"TimeStamp": base+pd.to_timedelta(ns, unit="ns"),
                            **{c: np.arange(4)+j for j,c in enumerate(COLS)}})
        rs, _ = records_from_frame(raw)
        self.assertEqual([len(r.x) for r in rs], [3,1])
        backward = raw.iloc[[1,0,2,3]]
        with self.assertRaises(ValueError):
            records_from_frame(backward)
        conflicting = pd.concat([raw.iloc[[0]], raw.iloc[[0]].assign(AI2_Current=999), raw.iloc[1:]])
        with self.assertRaises(ValueError):
            records_from_frame(conflicting)

    def test_vibration_dc_and_metadata_invariance(self):
        source = self.roles["evaluation"][:20]
        changed = [replace(r, x=r.x+np.array([100,-200,0]), start_m=r.start_m+10_000,
                           end_m=r.end_m+10_000, source_rows=()) for r in source]
        np.testing.assert_allclose(self.model.score(features(source)), self.model.score(features(changed)),
                                   rtol=1e-10, atol=1e-9)

    def test_sine_amplitude_residual_reconstruction(self):
        n=40
        basis=sine_basis(n)
        current=basis@np.array([2.,3.,4.])
        r=Record(10000,np.column_stack([np.arange(n),np.arange(n)**2,current]),0,1,2,())
        f=features([r])
        self.assertAlmostEqual(f.amplitude.iloc[0],5.)
        self.assertAlmostEqual(f.r2.iloc[0],1.)
        self.assertLess(f.i_residual.iloc[0],1e-13)

    def test_short_record_current_fallback(self):
        r=Record(10000,np.array([[9.,5.,10.]]),0,0,.5/60,())
        f=features([r])
        self.assertTrue(np.isnan(f.v0_rms.iloc[0]))
        self.assertFalse(self.model.condition(f)[0])
        self.assertTrue(np.isfinite(self.model.score(f)[0]))
        for name in ["C1d1","C1d2","C2d1","C2d2"]:
            np.testing.assert_allclose(Detector(name).fit(self.fit).score(f), Detector("B1").fit(self.fit).score(f))

    def test_fit_only_and_no_mutation(self):
        before=copy.deepcopy(self.model.parameters())
        f=features(self.roles["evaluation"])
        f.loc[:, "amplitude"] = 1e9
        f.loc[:, "v0_rms"] = 1e8
        self.model.score(f)
        self.assertEqual(before,self.model.parameters())
        self.assertFalse(self.model.condition(f).any())
        np.testing.assert_allclose(self.model.score(f), Detector("B1").fit(self.fit).score(f))

    def test_ridge_matches_mean_loss_optimizer(self):
        model=Detector("C1d2").fit(self.fit)
        f=self.fit.loc[model.condition(self.fit)]
        x=model.polynomial(f.amplitude.to_numpy())
        x=np.column_stack([np.ones(len(x)),(x-model.xmean)/model.xstd])
        y=model.pre.logs(f,"v0_rms")
        def fun(b):
            return np.mean((y-x@b)**2)+.001*np.sum(b[1:]**2)
        sol=minimize(fun,np.zeros(3),method="BFGS",tol=1e-10)
        np.testing.assert_allclose(model.beta[0],sol.x,rtol=1e-5,atol=1e-5)

    def test_length_scale_and_zero_scale(self):
        x=np.r_[np.arange(30),100+np.arange(29)]
        n=np.r_[np.full(30,40),np.full(29,10)]
        scaler=RobustLength().fit(x,n)
        self.assertIn((40,50),scaler.by_length)
        self.assertNotIn((10,19),scaler.by_length)
        self.assertTrue(np.isnan(RobustLength().fit(np.ones(30),np.full(30,30)).transform([1],[30])[0]))

    def test_calibration_ties_and_resolution(self):
        c=RankCalibration().fit([1,2,2,3,np.nan])
        np.testing.assert_allclose(c.p([0,1,2,2.5,3,4]),[1,1,.8,.4,.4,.2])
        self.assertEqual(c.excluded,1)
        self.assertIsNone(RankCalibration().fit(np.arange(77)).threshold(.01))
        c=RankCalibration().fit(np.arange(77))
        probes=np.array([c.threshold(.05),c.threshold(.05)+.01])
        np.testing.assert_array_equal(c.p(probes)<=.05,[False,True])

    def test_flat_quality_is_not_hidden_as_normal(self):
        r=copy.deepcopy(self.roles["evaluation"][0])
        r.x[:,0]=0
        f=features([r])
        self.assertTrue(f.quality.iloc[0])
        self.assertTrue(np.isfinite(self.model.score(f)[0]))

    def test_injection_identity_seed_target_energy(self):
        r=next(r for r in self.roles["evaluation"] if len(r.x)>=40)
        for family,target in [("band_noise",0),("damped_impulse",1),("current_residual",2)]:
            zero,_=self.generator.inject(r,family,target,0,11,2.)
            np.testing.assert_array_equal(r.x,zero.x)
            a,info=self.generator.inject(r,family,target,.5,11,2.)
            b,_=self.generator.inject(r,family,target,.5,11,2.)
            c,_=self.generator.inject(r,family,target,1.,11,2.)
            self.assertTrue(info["valid"])
            np.testing.assert_array_equal(a.x,b.x)
            other=[j for j in range(3) if j!=target]
            np.testing.assert_array_equal(a.x[:,other],r.x[:,other])
            np.testing.assert_allclose(c.x-r.x,2*(a.x-r.x),atol=1e-12)
            if family!="damped_impulse":
                self.assertAlmostEqual(np.sqrt(np.mean((a.x[:,target]-r.x[:,target])**2)),1.)
            else:
                self.assertAlmostEqual(np.abs(a.x[:,target]-r.x[:,target]).max(),1.)

    def test_injection_generator_fit_immutability(self):
        before=copy.deepcopy(self.generator.model.parameters())
        f=features(self.roles["evaluation"])
        self.generator.scales(f,"v0_rms")
        self.assertEqual(before,self.generator.model.parameters())

    def test_compound_breaks_condition_and_preserves_other_vibration(self):
        r=next(r for r in self.roles["evaluation"] if len(r.x)>=40)
        for mode in ["flat","distorted"]:
            injected,info=self.generator.inject(r,"compound_unavailable",0,.5,11,2.,mode)
            self.assertTrue(info["valid"])
            self.assertFalse(self.model.condition(features([injected]))[0])
            np.testing.assert_array_equal(injected.x[:,1],r.x[:,1])

    def test_no_empty_short_positive(self):
        r=Record(10000,np.array([[9.,5.,10.]]),0,0,.5/60,())
        for family,target in [("band_noise",0),("damped_impulse",1),("current_residual",2)]:
            _,info=self.generator.inject(r,family,target,1,11,2.)
            self.assertFalse(info["valid"])

    def test_foreign_parent_id_cannot_exclude_a_fit_neighbor(self):
        model=Detector("B3k5").fit(self.fit)
        a=self.fit.iloc[[0]].copy()
        b=a.copy()
        a["parent_key"]="external:0"
        b["parent_key"]="external:100000"
        b["parent"]=100000
        np.testing.assert_array_equal(model.score(a),model.score(b))

    def test_unavailable_condition_keeps_identical_point_score(self):
        source=self.roles["evaluation"]
        changed=[self.generator.inject(r,"compound_unavailable",0,1,11,.1,"flat")[0] for r in source]
        f=features(changed)
        self.assertFalse(self.model.condition(f).any())
        np.testing.assert_allclose(self.model.score(f),Detector("B1").fit(self.fit).score(f))


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    save_json(HERE/"evidence/contracts.json",dict(
        tested_utc=datetime.now(timezone.utc).isoformat(), tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),successful=result.wasSuccessful(),
        code_sha256={p.name:sha(p) for p in sorted(HERE.glob("*.py"))}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
