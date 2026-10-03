"""Read-only external adapters. Every external output is a TRAINING example."""
from __future__ import annotations

import io
import json
import zipfile
from collections import defaultdict

from basis import HERE, YEJUN, MASTER, CFG, np, pd, sha, save, waveform, bands, array_sha

WINDOW = CFG["shared_representation"]["source_window_samples"]


class Pool:
    def __init__(self, name):
        self.name = name
        self.vectors, self.ids, self.groups, self.normal = [], [], [], []

    def add(self, x, uid, group, normal, spectral=False):
        self.vectors.append(bands(x) if spectral else waveform(x))
        self.ids.append(f"{self.name}:{uid}")
        self.groups.append(str(group))
        self.normal.append(bool(normal))

    def finish(self, audit):
        x = np.asarray(self.vectors, dtype=float)
        if len(x) == 0 or len(set(self.ids)) != len(self.ids) or not np.isfinite(x).all():
            raise ValueError("Duplicate example ID or nonfinite external representation")
        result = dict(x=x, ids=np.asarray(self.ids), groups=np.asarray(self.groups),
                      normal=np.asarray(self.normal, dtype=bool))
        audit.update(examples=len(x), confirmed_normal_examples=int(sum(self.normal)),
                     source_groups=len(set(self.groups)),
                     confirmed_normal_groups=len(set(np.asarray(self.groups)[self.normal])),
                     representation_sha256=array_sha(x),
                     examples_are_independent_failures=False)
        return result, audit


def checked(item, inputs):
    path = YEJUN / item["path"]
    actual = sha(path)
    if actual != item["sha256"]:
        raise ValueError(f"Input hash mismatch: {path}")
    inputs.append(dict(path=item["path"], sha256=actual, bytes=path.stat().st_size))
    return path


def read_uci(inputs):
    receipt = json.loads((MASTER / "evidence/uci_acquisition.json").read_text())
    path = checked(receipt, inputs)
    pool = Pool("uci")
    with zipfile.ZipFile(path) as z:
        profiles = pd.read_csv(z.open("profile.txt"), sep="\t", header=None).to_numpy()
        waves = pd.read_csv(z.open("VS1.txt"), sep="\t", header=None).to_numpy()
    if waves.shape != (2205, 60) or not np.isfinite(waves).all():
        raise ValueError("Unexpected UCI structure")
    healthy = (profiles == [100, 100, 0, 130, 0]).all(axis=1)
    for i, x in enumerate(waves):
        pool.add(x[:WINDOW], f"cycle{i}:VS1:0", f"cycle{i}", healthy[i])
    return pool.finish(dict(raw_cycles=len(waves), healthy_cycles=int(healthy.sum()),
                            normal_definition="cooler=100, valve=100, pump leakage=0, accumulator=130, stable flag=0",
                            sensor="VS1, vibration magnitude, 1 Hz", unused_electrical="EPS1 is power, not current",
                            dropped_samples_per_cycle=60-WINDOW))


def read_skab(inputs):
    receipt = json.loads((MASTER / "evidence/skab_acquisition.json").read_text())
    paths = {item["source_path"]: checked(item, inputs) for item in receipt["files"]}
    reservation = json.loads((MASTER / "evidence/skab_group_reservation.json").read_text())
    members = defaultdict(list)
    for row in reservation["files"]:
        members[row["group_id"]].append(row["path"])
    pool, conflicts, raw_rows, unique_rows, leftovers = Pool("skab"), 0, 0, 0, 0
    for gid, files in sorted(members.items()):
        seen = {}
        for name in sorted(files):
            f = pd.read_csv(paths[name], sep=";")
            sensors = [c for c in f if c not in ("datetime", "anomaly", "changepoint")]
            t = pd.to_datetime(f.datetime).astype("int64").to_numpy()
            values = f[sensors].to_numpy(dtype=float)
            if np.any(np.diff(t) < 0) or not np.isfinite(values).all():
                raise ValueError("Invalid SKAB inputs")
            is_exception = name == "data/anomaly-free/anomaly-free.csv"
            a = f.anomaly.to_numpy() if "anomaly" in f else np.zeros(len(f)) if is_exception else None
            c = f.changepoint.to_numpy() if "changepoint" in f else np.zeros(len(f)) if is_exception else None
            if a is None or c is None or not np.isin(a, [0, 1]).all() or not np.isin(c, [0, 1]).all():
                raise ValueError("Unexpected SKAB labels")
            raw_rows += len(f)
            for i in range(len(f)):
                key = (int(t[i]), *values[i].tolist())
                row = seen.setdefault(key, dict(t=int(t[i]), v=[f.Accelerometer1RMS.iloc[i], f.Accelerometer2RMS.iloc[i]], labels=set()))
                row["labels"].add((int(a[i]), int(c[i])))
        rows = sorted(seen.values(), key=lambda r: r["t"])
        unique_rows += len(rows)
        conflicts += sum(len(r["labels"]) > 1 for r in rows)
        t = np.array([r["t"] for r in rows], dtype=np.int64)
        if np.any(np.diff(t) <= 0):
            raise ValueError("Conflicting SKAB time/value observations")
        dt = float(np.median(np.diff(t)))
        boundaries = np.r_[0, np.flatnonzero(np.diff(t) > 1.5*dt)+1, len(rows)]
        for segment, (lo, hi) in enumerate(zip(boundaries[:-1], boundaries[1:])):
            for offset in range(lo, hi, WINDOW):
                group = rows[offset:min(offset+WINDOW, hi)]
                if len(group) < 4:
                    leftovers += len(group)
                    continue
                healthy = all(len(r["labels"]) == 1 and next(iter(r["labels"]))[0] == 0 for r in group)
                for axis in range(2):
                    x = np.array([r["v"][axis] for r in group])
                    pool.add(x, f"{gid}:{segment}:{offset}:{axis}", gid, healthy)
    if conflicts != 237:
        raise ValueError(f"Expected prior 237 label conflicts, got {conflicts}")
    return pool.finish(dict(files=len(paths), captures=len(members), raw_rows=raw_rows,
                            unique_observations=unique_rows, conflicts=conflicts,
                            leftover_rows=leftovers, sensors="two RMS-envelope channels; not raw vibration",
                            previous_split_roles="all converted to external training for this separate experiment"))


def read_beihang(inputs):
    receipt = json.loads((MASTER / "evidence/beihang_acquisition.json").read_text())
    path = checked(receipt["files"][0], inputs)
    pool, inventory = Pool("beihang"), []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".csv"))
        for name in names:
            print(f"prepare Beihang {name.split('/')[-2:]}", flush=True)
            header = pd.read_csv(z.open(name), nrows=0).columns.tolist()
            aliases = [("X vibration", "振动X_m/s2"), ("Y vibration", "振动Y_m/s2"), ("Z vibration", "振动Z_m/s2")]
            axes = [next(c for c in candidates if c in header) for candidates in aliases]
            pairs = [(header[header.index(axis)-1], axis) for axis in axes]
            f = pd.read_csv(z.open(name), usecols=[c for pair in pairs for c in pair])
            healthy = "/Healthy state/" in name
            for time_col, axis in pairs:
                pair = f[[time_col, axis]].dropna().to_numpy(dtype=float)
                if not np.isfinite(pair).all():
                    raise ValueError("Invalid Beihang channel")
                diff = np.diff(pair[:, 0])
                dt = np.median(diff[diff > 0])
                cuts = np.r_[0, np.flatnonzero((diff <= 0) | (diff > 1.5*dt))+1, len(pair)]
                starts = []
                for lo, hi in zip(cuts[:-1], cuts[1:]):
                    starts.extend(range(lo, hi-WINDOW+1, WINDOW))
                selected = np.linspace(0, len(starts)-1, min(256, len(starts)), dtype=int)
                for i in selected:
                    start = starts[i]
                    pool.add(pair[start:start+WINDOW, 1], f"{name}:{axis}:{start}", name, healthy)
                inventory.append(dict(file=name, axis=axis, raw_samples=len(pair), contiguous_segments=len(cuts)-1,
                                      candidate_windows=len(starts), retained_windows=len(selected),
                                      positive_dt_median=float(dt), healthy=healthy))
    return pool.finish(dict(files=len(names), healthy_files=2, inventory=inventory,
                            sensors="independent raw vibration axes; no fabricated current channel"))


def read_espset(inputs):
    receipt = json.loads((MASTER / "evidence/espset_acquisition.json").read_text())
    paths = {item["path"].split("/")[-1]: checked(item, inputs) for item in receipt["files"]}
    with zipfile.ZipFile(paths["features.zip"]) as z:
        f = pd.read_csv(z.open("features.csv"), sep=";")
    ids = f.id.to_numpy()
    if not (np.array_equal(ids, np.arange(len(f))) or np.array_equal(ids, np.arange(1, len(f)+1))):
        raise ValueError("ESPset spectrum-feature row alignment cannot be assumed")
    pool = Pool("espset")
    with zipfile.ZipFile(paths["spectrum.zip"]) as z:
        with io.TextIOWrapper(z.open("spectrum.csv"), encoding="utf-8-sig") as stream:
            n = 0
            for i, line in enumerate(stream):
                x = np.fromstring(line.strip(), sep=";")
                if len(x) != 12103 or i >= len(f):
                    raise ValueError("ESPset spectrum width or row mapping changed")
                pool.add(x, f"spectrum:{ids[i]}", f"pump:{f.esp_id.iloc[i]}", f.label.iloc[i] == "Normal", spectral=True)
                n += 1
                if n % 1000 == 0:
                    print(f"prepare ESPset {n}/{len(f)}", flush=True)
    if n != len(f):
        raise ValueError("ESPset spectrum-feature length mismatch")
    return pool.finish(dict(spectrum_rows=n, frequency_bins=12103, labels=f.label.value_counts().to_dict(),
                            alignment="sequential id verified against spectrum row ordinal",
                            sensors="speed-normalized vibration velocity spectrum; no time waveform reconstructed"))


def prepare():
    cache = HERE / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    inputs, audit = [], {}
    for name, reader in [("uci", read_uci), ("skab", read_skab), ("beihang", read_beihang), ("espset", read_espset)]:
        print(f"prepare {name}", flush=True)
        pool, audit[name] = reader(inputs)
        np.savez_compressed(cache / f"{name}.npz", **pool)
        audit[name]["cache_sha256"] = sha(cache / f"{name}.npz")
        print(f"{name}: {audit[name]['examples']} all, {audit[name]['confirmed_normal_examples']} normal", flush=True)
    result = dict(sources=audit, inputs=inputs, code_sha256=sha(__file__), representation_code_sha256=sha(HERE / "basis.py"),
                  protocol_sha256=sha(HERE / "protocol.json"), external_inputs_are_training_only=True)
    save(HERE / "evidence/source_audit.json", result)
    return result


if __name__ == "__main__":
    prepare()
