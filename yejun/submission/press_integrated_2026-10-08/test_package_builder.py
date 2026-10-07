"""Guard the packaging invariants against silent numerical or path changes."""
import importlib.util
from pathlib import Path
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location("integrated_package_builder", Path(__file__).with_name("build_package.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_excluded_branches_do_not_change_retained_calculations():
    source = builder.read(builder.SOURCE / "frontier_model.py")
    packaged = builder.strip_reference_frontier(source)
    assert "REF_" not in packaged and "reference_" not in packaged
    assert builder.retained_calculation_ast(source) == builder.retained_calculation_ast(packaged)
    changed = packaged.replace('spec["weight"] * y', '2 * spec["weight"] * y')
    assert changed != packaged
    assert builder.retained_calculation_ast(source) != builder.retained_calculation_ast(changed)


def test_runner_packaging_changes_counts_and_locked_files_only():
    source = builder.read(builder.SOURCE / "run_experiment.py")
    packaged = builder.strip_reference_run(source)
    assert 'candidates=56' in packaged
    assert "competitor_reference.py" not in packaged
    assert builder.retained_calculation_ast(source) == builder.retained_calculation_ast(packaged)


def test_only_the_single_anonymous_metadata_keyword_is_removed():
    source = builder.read(builder.ROOT / "claude/code/press/domain/05_supervised_confound.py")
    packaged = builder.strip_anonymous_metadata(source)
    assert "competitor=" not in packaged
    assert len(source.splitlines()) == len(packaged.splitlines()) + 1
    with pytest.raises(AssertionError, match="Unexpected content"):
        builder.strip_anonymous_metadata(source.replace('f1=0.944', 'f1=0.950'))


def test_archive_cannot_escape_destination(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("package/../../outside.py", "invalid")
    with pytest.raises(ValueError, match="Unsafe archive"):
        builder.extract_original(archive, tmp_path / "destination")
    assert not (tmp_path / "outside.py").exists()


def test_fitted_state_is_not_shipped_as_reproduction(tmp_path):
    archive = tmp_path / "cached.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("package/code/weights.pkl", b"not a pickle")
    with pytest.raises(ValueError, match="Precomputed fitted state"):
        builder.extract_original(archive, tmp_path / "destination")


def test_historical_selection_and_sources_remain_valid():
    lock = builder.verify_historical_lock()
    assert lock["selected"] == "V2+VD3@1"
    assert lock["lock_sha256"] == "20c992cd930c02c59f3ef4d3b7cccc1b15e2f3eda1fd78065fd06452a3c1ce2b"
