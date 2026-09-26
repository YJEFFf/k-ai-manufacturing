"""verify.py: 신선도 판정(실행하지 않은 산출물은 실패)과 JSON 비교."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import verify as V


def _write_manifest(out: Path, a: float, b: float):
    out.mkdir(parents=True, exist_ok=True)
    (out / "run_manifest.json").write_text(json.dumps({"last_full_run": {
        "started_epoch": a, "finished_epoch": b, "started_at": "s", "finished_at": "f"}}), encoding="utf-8")


def test_freshness_detects_files_outside_last_full_run(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    monkeypatch.setattr(V, "OUT", out)
    now = time.time()
    _write_manifest(out, now - 100, now - 10)
    f = out / "cv" / "x.csv"
    f.parent.mkdir(parents=True)
    f.write_text("a\n1\n", encoding="utf-8")
    os.utime(f, (now - 50, now - 50))
    ok, _ = V.freshness([Path("cv/x.csv")])
    assert ok
    os.utime(f, (now, now))  # 실행 기록보다 늦게 쓰인 파일(예: 막 받은 사본)
    ok, msg = V.freshness([Path("cv/x.csv")])
    assert not ok and "밖에서" in msg


def test_freshness_requires_full_run_record(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(V, "OUT", out)
    (out / "run_manifest.json").write_text(json.dumps({"last_full_run": None}), encoding="utf-8")
    ok, msg = V.freshness([])
    assert not ok and "전체 실행" in msg


def test_cmp_json_tolerance_and_skip_keys():
    a = {"x": 1.0, "timings_s": {"m": 1}, "l": [1, 2]}
    b = {"x": 1.0 + 1e-9, "timings_s": {"m": 999}, "l": [1, 2]}
    assert V.cmp_json(a, b) == []
    assert V.cmp_json({"x": 1.0}, {"x": 1.1})


def test_packaged_copy_is_not_fresh_until_rerun(tmp_path, monkeypatch):
    """제출 묶음(packaged_epoch)은 그 뒤의 전체 실행 기록이 있어야 신선하다(unzip이 파일 시각을 보존해도)."""
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(V, "OUT", out)
    now = time.time()
    (out / "run_manifest.json").write_text(json.dumps({"packaged_epoch": now, "last_full_run": {
        "started_epoch": now - 100, "finished_epoch": now - 10, "finished_at": "f"}}), encoding="utf-8")
    ok, msg = V.freshness([])
    assert not ok and "제출 묶음" in msg


def test_code_change_after_run_is_not_fresh(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(V, "OUT", out)
    now = time.time()
    (out / "run_manifest.json").write_text(json.dumps({"last_full_run": {
        "started_epoch": now - 100, "finished_epoch": now + 100, "finished_at": "f", "code_sha256": "0" * 64}}),
        encoding="utf-8")
    ok, msg = V.freshness([])
    assert not ok and "코드" in msg
