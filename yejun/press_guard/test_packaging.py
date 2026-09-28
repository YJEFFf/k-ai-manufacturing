"""목록 사본에서 끊긴 문서 링크가 빠지지 않도록 검사한다."""
import importlib.util
from pathlib import Path

import pandas as pd


def test_relative_document_links_must_be_included(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("package_link_test", Path(__file__).parent / "tools" / "package_manifest.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    monkeypatch.setattr(package, "REPO", tmp_path)
    docs = tmp_path / "docs"; docs.mkdir()
    (docs / "README.md").write_text(
        "[값](values.csv#column)\n![그림](<plot image.png>)\n[참고][ref]\n"
        "[ref]: values.csv\n[앵커](#here)\n[외부](https://example.com/info)\n"
        "```python\n'[실행 예시](does-not-exist)'\n```\n", encoding="utf-8")
    (docs / "values.csv").write_text("a\n1\n", encoding="utf-8")
    (docs / "plot image.png").write_bytes(b"fixture")
    table = pd.DataFrame({"path": ["docs/README.md", "docs/values.csv", "docs/plot image.png"]})
    assert package.document_link_checks(table) == []
    errors = package.document_link_checks(table[~table.path.str.endswith("values.csv")])
    assert len(errors) == 2 and all("values.csv" in e for e in errors)
