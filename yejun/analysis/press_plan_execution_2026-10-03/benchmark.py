"""Registered same-machine batch sweeps including feature extraction, excluding I/O."""
import pickle
import time
from common import core, load_press, np, csv, save, environment


def numeric_elements(obj, visited=None):
    visited = set() if visited is None else visited
    if id(obj) in visited:
        return 0
    visited.add(id(obj))
    if isinstance(obj, np.ndarray):
        return obj.size if obj.dtype.kind in "biufc" else 0
    if isinstance(obj, (int, float, np.number)):
        return 1
    if isinstance(obj, dict):
        return sum(numeric_elements(v, visited) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(numeric_elements(v, visited) for v in obj)
    if hasattr(obj, "__dict__"):
        return numeric_elements(vars(obj), visited)
    return 0


def run(output):
    models = pickle.loads((output.parent / "artifacts/press_development.pkl").read_bytes())["P0"]
    normal, _ = load_press()
    records = core.split_records(normal, "P0")["evaluation"]
    results = []
    for name, model in models.items():
        if name.startswith("A1"):
            continue
        for _ in range(5):
            model.predict(core.features(records))
        times = []
        for _ in range(20):
            start = time.perf_counter_ns()
            model.predict(core.features(records))
            times.append((time.perf_counter_ns()-start)/len(records)/1e6)
        refs = [model.reference]
        if hasattr(model, "conditional_reference"):
            refs.append(model.conditional_reference)
        if hasattr(model.model, "reference"):
            refs.append(model.model.reference)
        results.append(dict(model=name, batch_size=len(records), measured_sweeps=20, warmup_sweeps=5,
                            median_ms_per_record=float(np.median(times)), numeric_state_elements=numeric_elements(model),
                            reference_bytes=sum(a.nbytes for a in refs), checkpoint_bytes=len(pickle.dumps(model, protocol=5))))
    csv(output / "inference_cost.csv", results)
    save(output / "inference_cost_environment.json", environment())
