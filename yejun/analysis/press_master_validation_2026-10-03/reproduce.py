"""Run contracts and all experiments in a temporary output tree and compare.

Original results and original run dates remain intact. Only the reproduction
receipt and ignored log are written beside them. No external test is opened.
"""
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import shutil
import tempfile
import unittest

import numpy as np
import pandas as pd
import scipy

import core
import run
import revise
import diagnose
import summarize
from test_contracts import Contracts
from test_revision import RevisionContracts


def main():
    source=core.HERE
    log=io.StringIO()
    checks=[]
    started=datetime.now(timezone.utc).isoformat()
    tests=unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(Contracts),
        unittest.defaultTestLoader.loadTestsFromTestCase(RevisionContracts)])
    test_result=unittest.TextTestRunner(stream=log,verbosity=2).run(tests)
    if not test_result.wasSuccessful():
        raise RuntimeError(log.getvalue())
    with tempfile.TemporaryDirectory(prefix="press-master-reproduction-") as temporary:
        output=Path(temporary)
        (output/"cache").mkdir()
        # This output tree contains byte-identical design/code receipts. Modules
        # remain imported from source: core.ROOT still names the real data root.
        for p in list(source.glob("*.py"))+list(source.glob("design_*.json")):
            shutil.copy2(p,output/p.name)
        for module in [run,revise,diagnose,summarize]:module.HERE=output
        with contextlib.redirect_stdout(log):
            run.run_development()
            run.run_audit()
            diagnose.main()
            revise.development()
            revise.audit()
            summarize.main()
        candidates=[]
        for version in ["v1","v2"]:
            candidates+=list((source/"evidence"/version).glob("*.csv"))
            candidates+=[source/"evidence"/version/name for name in ["model_parameters.json","selection.json"]]
        candidates+=list((source/"evidence/diagnosis").glob("*.csv"))
        candidates+=[source/"evidence"/name for name in ["comparison.csv","representative_target_pod.csv","conclusions.json"]]
        for original in sorted(candidates):
            relative=original.relative_to(source)
            regenerated=output/relative
            checks.append(dict(path=str(relative),matches=core.sha(original)==core.sha(regenerated),
                               expected_sha256=core.sha(original),reproduced_sha256=core.sha(regenerated)))
    (source/"cache").mkdir(exist_ok=True)
    (source/"cache/reproduction.log").write_text(log.getvalue())
    for module in [run,revise,diagnose,summarize]:module.HERE=source
    passed=all(c["matches"] for c in checks)
    result=dict(status="pass" if passed else "fail",started_utc=started,
        completed_utc=datetime.now(timezone.utc).isoformat(),
        scope="24 computational contracts and fresh refit/injection/aggregation replay; not model admission or external validation",
        tests=test_result.testsRun,test_failures=len(test_result.failures),test_errors=len(test_result.errors),
        compared_files=len(checks),comparisons=checks,
        environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__),
        code_sha256={p.name:core.sha(p) for p in sorted(source.glob("*.py"))},
        design_sha256={p.name:core.sha(p) for p in sorted(source.glob("design_*.json"))})
    core.save_json(source/"evidence/reproduction.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in ["comparisons","code_sha256","design_sha256"]},indent=2))
    if not passed:raise SystemExit(1)


if __name__=="__main__":main()
