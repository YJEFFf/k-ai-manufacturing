"""Static plan checks and mathematical counterexamples on INVENTED arrays only.

Does not load press/SKAB/Beihang/ESP measurements, fit a detector, generate a
held-out data perturbation, or inspect any previously sealed model performance.
These are specification checks, not tests of a future product implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import re
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "evidence/plan_contract_verification.json"


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key {key} in {path}")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def rank(values, query):
    return Fraction(1 + sum(value >= query for value in values), len(values) + 1)


def k1(bcal, ccal, sb, sc, gate, alpha):
    minimum = math.ceil(1 / alpha) - 1
    if not math.isfinite(sb) or len(bcal) < minimum:
        return None, "unsupported"
    if gate and math.isfinite(sc) and len(ccal) >= max(39, minimum):
        return rank(ccal, sc), "conditional_reference"
    return rank(bcal, sb), "baseline_reference"


def replay(bits, times, persistent=False):
    """Small independent interpretation for checking the written state rules."""
    active = False
    history, starts, closes = [], [], []
    negatives = 0
    previous = None
    for index, (bit, now) in enumerate(zip(bits, times)):
        if previous is not None and now - previous > 30:
            if active:
                closes.append((previous + 30, "unknown_gap"))
            active, history, negatives = False, [], 0
        previous = now
        if bit is None:
            if active:
                closes.append((now, "unknown_quality"))
            active, history, negatives = False, [], 0
            continue
        history = (history + [bit])[-3:]
        negatives = negatives + 1 if bit == 0 else 0
        if active and negatives >= 2:
            closes.append((now, "two_negative"))
            active, history, negatives = False, [], 0
        if not active and bit == 1 and (not persistent or sum(history) >= 2):
            starts.append((index, now))
            active = True
    if active:
        closes.append((times[-1], "right_censored"))
    return starts, closes


def phase_rotate(wave, delta):
    if delta == 0:
        return wave.copy()
    n = len(wave)
    mean = wave.mean()
    spectrum = np.fft.rfft(wave - mean)
    end = -1 if n % 2 == 0 else None
    spectrum[1:end] *= np.exp(1j * delta)
    return np.fft.irfft(spectrum, n=n) + mean


def main():
    checks, failures = [], []

    def check(name, ok):
        checks.append(name)
        if not bool(ok):
            failures.append(name)

    spec = read(HERE / "execution_contracts.json")
    base = read(HERE / "protocol.json")
    state = read(HERE / "execution_revision.json")
    review = read(HERE / "evidence/plan_review.json")
    check("frozen original numeric protocol unchanged", hashlib.sha256(
        (HERE / "protocol.json").read_bytes()).hexdigest() == spec["original_protocol_sha256"])
    check("current status references completed contract", state["current_numeric_contract"] ==
          "execution_contracts.json" and state["authoritative_execution_document"] ==
          spec["authoritative_document"])
    check("no new data performance claimed", not state["design_revision_performance_run"] and
          not spec["data_access"]["new_performance_computed_in_design_revision"])
    check("no final model manufactured", state["current_status"]["final_model"] is None and
          state["current_status"]["new_candidates_meeting_all_admission_gates"] == 0 and
          not spec["completion_states"]["candidate_admitted"])
    check("reports remain unauthorized", not spec["artifacts"]["report_and_slides_authorized"])
    mapping = {"minimum_normal_reduction": "minimum_normal_requests_reduced",
               "maximum_ten_minute_increase": "maximum_additional_requests_per_10min",
               "minimum_gain_pp": "minimum_pod_gain_pp_in_two_development_families",
               "maximum_loss_pp": "maximum_pod_loss_pp_per_preregistered_loss_cell",
               "minimum_distinct_supported_parents": "minimum_distinct_parents_per_pod_cell"}
    for new, old in mapping.items():
        check(f"admission preserved: {new}", spec["selection"][new] == base["selection"][old])
    check("augmentation seeds and ratios retained", spec["budget"]["seeds"] ==
          base["random_seeds"] and spec["budget"]["normal_augmentation_ratios"] == [0.5, 1.0])
    check("no best-seed selection", spec["budget"]["deployment_seed"] == 11 and
          spec["selection"]["augmentation_each_seed_must_pass"])
    check("augmentation training and injection seeds are separate full axes",
          spec["augmentation"]["training_seeds"] == [11, 29, 47] and
          spec["augmentation"]["evaluation_injection_seeds"] == [11, 29, 47] and
          "full 3 training x 3 injection" in spec["augmentation"]["seed_crossing"])
    check("no-candidate branch completes reference audits", spec["selection"]["no_candidate"] ==
          dict(selected_candidate=None, comparison_reference="B1", improvement_established=False,
               continue_fixed_reference_audits=True, restore_v2=False))
    done = set()
    for stage in spec["stages"]:
        check(f"acyclic dependencies {stage['id']}", set(stage["depends_on"]) <= done)
        check(f"unique stage {stage['id']}", stage["id"] not in done)
        done.add(stage["id"])
    check("six bounded stages", done == {f"E{i}" for i in range(1, 7)})
    check("one new correction", spec["budget"]["new_score_calibration_candidates"] == ["K1"])
    check("conditional calibration numerical contract", spec["K1"]["minimum_conditional_cal"] == 39
          and not spec["K1"]["union_or_min_of_p"] and not spec["K1"]["overall_alpha_guarantee"])
    check("policy parameters bound to interpreted state machine", spec["policy"]["reset_gap_seconds"] == 30
          and spec["policy"]["reset_gap_comparison"] == ">"
          and spec["policy"]["resolve_after_negatives"] == 2
          and spec["policy"]["clear_history_on_resolve"])
    check("policy selectors use no-loss and one extra decision", all(
          spec["policy"]["selectors"][part]["maximum_extra_valid_decisions"] == 1
          and spec["policy"]["selectors"][part]["no_lost_I0_detected_event"] for part in ["press", "skab"]))
    check("external budget agrees with current status", spec["budget"]["skab_max_structures"] ==
          state["external_first_comparison"]["maximum_structures_after_press_selection"] == 3)
    acquisition = read(HERE / "evidence/skab_acquisition.json")
    exception = spec["skab"]["normal_label_exception"]
    found = [row for row in acquisition["files"] if row["source_path"] == exception["source_path"]]
    check("normal-only label exception uses exact pinned source hash", len(found) == 1 and
          found[0]["sha256"] == exception["sha256"] and exception["anomaly"] == exception["changepoint"] == 0)
    reservation = read(HERE / "evidence/skab_group_reservation.json")
    check("reserved group counts unchanged", spec["skab"]["group_counts"] == reservation["split_group_counts"])
    check("head never uses future calibration rank", "fit-only" in spec["probability"]["K1_input"]
          and spec["probability"]["normal_threshold_cal_separate_from_main_P2"])
    check("probability gain requires full evaluation coverage", "100% evaluation support" in
          spec["probability"]["primary_claim"] and "null with full denominator" in
          spec["probability"]["missing_evaluation_probability"])
    check("H2 is deterministic negative control", not spec["future_injections"]["H2"]["stochastic"]
          and not spec["future_injections"]["H2"]["selection_use"])
    check("Beihang padding distinguished", "one-sided empty is input error" in spec["beihang"]["paired_empty_cells"])
    check("all review findings closed or explicitly excluded", all(row["status"] in
          {"resolved_in_design", "excluded_from_scope"} for row in review["findings"]))
    check("review finding IDs unique", len({row["id"] for row in review["findings"]}) ==
          len(review["findings"]))
    check("remaining unknowns require measurements or external evidence", all(row["kind"] in
          {"execution_result", "external_evidence"} for row in review["remaining_unknowns"]))
    for path in sorted(HERE.glob("*.json")):
        read(path)
        check(f"strict JSON {path.name}", True)
    for path in sorted(HERE.glob("*.md")):
        content = path.read_text()
        check(f"balanced code fences {path.name}", content.count("```") % 2 == 0)
        for link in re.findall(r"\[[^\]]*\]\(([^)\n]+)\)", content):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
                continue
            target = path.parent / link.split("#", 1)[0].strip("<>")
            check(f"local link {path.name}: {link}", target.exists() or target == OUT)
    all_docs = "\n".join(path.read_text() for path in HERE.glob("*.md"))
    for stale in ["새 모델은 아직 구현·학습하지 않았다", "둘 다 필수. 개선을 주장하려면",
                  "첫 비교는 B1·조건부 후보·kNN과 선택된 증강 변형까지 최대 4개다",
                  "구현 전 이 명세가 없으면"]:
        check(f"obsolete instruction removed: {stale}", stale not in all_docs)

    # Rational ranks expose <= and tie boundaries without floating approximations.
    for n in [19, 39, 77, 156]:
        calibration = list(range(n))
        for query in [-1, n - 1, n, n + 1]:
            for alpha in [Fraction(1, 20), Fraction(3, 100), Fraction(1, 100)]:
                value, route = k1(calibration, list(range(100)), query, 200, False, alpha)
                if n >= math.ceil(1 / alpha) - 1:
                    check(f"B1 fallback invariant n={n} q={query} alpha={alpha}",
                          value == rank(calibration, query) and route == "baseline_reference")
                else:
                    check(f"unsupported rank retained n={n} q={query} alpha={alpha}", value is None)
    check("19-cal boundary above max triggers at 5%", rank(range(19), 20) == Fraction(1, 20))
    check("19-cal tied maximum does not trigger", rank(range(19), 18) > Fraction(1, 20))
    check("38 conditional parents use exact B1", k1(range(77), range(38), 78, 200, True,
          Fraction(1, 20)) == (Fraction(1, 78), "baseline_reference"))
    check("39 conditional parents support primary route", k1(range(77), range(39), 0, 40, True,
          Fraction(1, 20)) == (Fraction(1, 40), "conditional_reference"))
    check("39 not enough for 1% conditional tail", k1(range(156), range(39), 160, 40, True,
          Fraction(1, 100))[1] == "baseline_reference")
    check("K1 never ORs the two paths", k1(range(77), range(39), 78, -1, True,
          Fraction(1, 20)) == (Fraction(1, 1), "conditional_reference"))
    check("nonfinite query cannot become smallest rank", k1(range(77), range(39),
          math.nan, 1, False, Fraction(1, 20)) == (None, "unsupported"))
    check("unavailable conditional query takes finite B1", k1(range(77), range(39),
          78, math.nan, True, Fraction(1, 20)) == (Fraction(1, 78), "baseline_reference"))

    cases = [
        ([1, 1, 0, 0, 1], [0, 1, 2, 3, 4], False, [0, 4]),
        ([1, 1, 0, 0, 1], [0, 1, 2, 3, 4], True, [1]),
        ([1, 0, 1], [0, 1, 2], True, [2]),
        ([1, 1, 0], [0, 1, 2], True, [1]),
        ([1, 1, None, 1], [0, 1, 2, 3], True, [1]),
        ([1, 1], [0, 30], True, [1]),
        ([1, 1], [0, 30.001], True, []),
        ([0, 0, 0], [0, 1, 2], True, []),
    ]
    for index, (bits, times, persistent, expected) in enumerate(cases):
        starts, _ = replay(bits, times, persistent)
        check(f"state machine counterexample {index}", [i for i, t in starts] == expected)
    check("gap occupancy closes at timer", replay([1, 0], [0, 40])[1] == [(30, "unknown_gap")])
    check("EOF no invented trailing 30 seconds", replay([1], [5])[1] == [(5, "right_censored")])
    check("two-negative close clears stale votes", replay([1, 1, 0, 0, 1, 0],
          list(range(6)), True)[0] == [(1, 1)])
    check("single isolated detection cannot be hidden by P23",
          len(replay([0, 1, 0], [0, 1, 2])[0]) == 1 and
          len(replay([0, 1, 0], [0, 1, 2], True)[0]) == 0)

    # Distinct-parent nearest distances: copies cannot create additional neighbors.
    def parent_distance(values, k, exclude=None):
        distances = {}
        for parent, value in values:
            if parent != exclude:
                distances[parent] = min(distances.get(parent, math.inf), abs(value))
        return sum(sorted(distances.values())[:k]) / k if len(distances) >= k else None
    original = [(str(i), i + 1.0) for i in range(6)]
    check("A1 identity with repeated parents", parent_distance(original, 5) ==
          parent_distance(original * 4, 5))
    check("all children of own parent excluded", parent_distance(original + [("0", 0)], 5, "0") == 4)
    check("fewer than 5 parents is unsupported", parent_distance(original[:4] * 5, 5) is None)
    for n in [1, 19, 20, 21, 30, 40, 50]:
        legal = [(length, start) for length in [20, 30, 40] if length < n
                 for start in range(n - length + 1)]
        check(f"proper crop has no padding or whole copy n={n}", all(0 <= s and s + l <= n and l < n
              for l, s in legal))
        check(f"short-parent crop support n={n}", bool(legal) == (n > 20))
    for n, m in [(81, 50), (158, 90), (316, 200)]:
        previous = [0] * m
        for ratio in [.5, 1.0]:
            total = math.floor(ratio * n)
            quotas = [total // m + (i < total % m) for i in range(m)]
            check(f"crop quota conservation {n}/{ratio}", sum(quotas) == total and max(quotas) - min(quotas) <= 1)
            check(f"ratio prefix allocation {n}/{ratio}", all(a >= b for a, b in zip(quotas, previous)))
            previous = quotas

    # All labels compatible with [L,U], independently enumerate confusion bounds.
    for bits in itertools.product([0, 1], repeat=3):
        low, high = [0, 1, 0], [1, 1, 1]
        outcomes = []
        for labels in itertools.product(*[range(l, u + 1) for l, u in zip(low, high)]):
            tp = sum(b * y for b, y in zip(bits, labels))
            fp = sum(b * (1 - y) for b, y in zip(bits, labels))
            fn = sum((1 - b) * y for b, y in zip(bits, labels))
            outcomes.append((tp, fp, fn, Fraction(2 * tp, 2 * tp + fp + fn)))
        tp_lo, tp_hi = sum(b*l for b,l in zip(bits,low)), sum(b*u for b,u in zip(bits,high))
        fp_lo, fp_hi = sum(b*(1-u) for b,u in zip(bits,high)), sum(b*(1-l) for b,l in zip(bits,low))
        fn_lo, fn_hi = sum((1-b)*l for b,l in zip(bits,low)), sum((1-b)*u for b,u in zip(bits,high))
        check(f"ambiguous confusion extrema {bits}",
              [min(r[i] for r in outcomes) for i in range(3)] == [tp_lo, fp_lo, fn_lo] and
              [max(r[i] for r in outcomes) for i in range(3)] == [tp_hi, fp_hi, fn_hi])
        check(f"ambiguous F1 extrema {bits}", min(r[3] for r in outcomes) ==
              Fraction(2*tp_lo, 2*tp_lo+fp_hi+fn_hi) and max(r[3] for r in outcomes) ==
              Fraction(2*tp_hi, 2*tp_hi+fp_lo+fn_lo))

    rng = np.random.Generator(np.random.PCG64(713))
    for n in [20, 21, 40, 41, 50, 51]:
        wave = 7 + rng.normal(size=n)
        before = np.fft.rfft(wave - wave.mean())
        check(f"H2 zero returns byte-identical n={n}", wave.tobytes() == phase_rotate(wave, 0).tobytes())
        for delta in [-math.pi/3, -math.pi/6, math.pi/6, math.pi/3]:
            changed = phase_rotate(wave, delta)
            after = np.fft.rfft(changed - changed.mean())
            check(f"H2 real, shape, DC n={n} delta={delta}", np.isrealobj(changed) and
                  changed.shape == wave.shape and abs(changed.mean()-wave.mean()) < 1e-12)
            check(f"H2 magnitude invariant n={n} delta={delta}",
                  np.allclose(abs(after), abs(before), rtol=1e-10, atol=1e-12))
            check(f"H2 RMS-only input invariant n={n} delta={delta}",
                  np.isclose(np.std(changed), np.std(wave), rtol=1e-10, atol=1e-12))
            if n % 2 == 0:
                check(f"H2 Nyquist invariant n={n} delta={delta}", abs(after[-1]-before[-1]) < 1e-10)
            else:
                check(f"H2 odd last bin rotates n={n} delta={delta}",
                      abs(after[-1]-before[-1]*np.exp(1j*delta)) < 1e-10)
    for length in [20, 60]:
        for amp in [.25, .5]:
            scale = 1 + amp*np.arange(length)/(length-1)
            check(f"T1 declared endpoints and monotonicity {length}/{amp}", scale[0] == 1 and
                  scale[-1] == 1+amp and np.all(np.diff(scale) > 0))

    # Probability objective weights and constant-score optimum do not depend on labels in cal.
    for q in [.01, .05, .1, .2]:
        n0, n1 = 13, 4
        count = n0+n1
        weights = np.array([count*(1-q)/n0]*n0 + [count*q/n1]*n1)
        labels = np.array([0]*n0+[1]*n1)
        p = 1/(1+np.exp(-math.log(q/(1-q))))
        check(f"head weight normalization q={q}", abs(weights.sum()-count) < 1e-12)
        check(f"constant-score optimum intercept q={q}", abs(np.dot(weights, p-labels)/count) < 1e-12)
        check(f"positive prior exactly q={q}", abs(weights[labels==1].sum()/count-q) < 1e-12)
    for eta, label in [(1000., 0), (1000., 1), (-1000., 0), (-1000., 1)]:
        loss = np.logaddexp(0, eta)-label*eta
        check(f"stable BCE at extreme logit {eta}/{label}", np.isfinite(loss) and loss >= 0)

    hashed_paths = sorted(HERE.glob("*.md")) + sorted(HERE.glob("*.json")) + [
        Path(__file__), HERE / "evidence/plan_review.json"]
    receipt = dict(status="pass" if not failures else "fail",
                   checked_at_utc=datetime.now(timezone.utc).isoformat(),
                   scope="Static specifications and mathematical checks on invented arrays only; no new real-data performance evaluation",
                   python=platform.python_version(), numpy=np.__version__,
                   checks=len(checks), failures=failures, check_names=checks,
                   input_hashes={str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in hashed_paths})
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k:v for k,v in receipt.items() if k not in {"check_names","input_hashes"}}, ensure_ascii=False, indent=2))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
