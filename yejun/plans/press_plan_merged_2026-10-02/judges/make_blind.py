import re, shutil, pathlib, sys
ROOT = pathlib.Path("/Volumes/YJSSD/공모전/k-제조데이터/yejun/plans")
SP = pathlib.Path(sys.argv[1])
CL = ROOT / "press_research_claude_2026-10-01"
CX = ROOT / "press_research_2026-10-01"

def sanitize_claude_readme(t):
    t = t.replace("# 프레스 유압펌프 과제 재설계 계획 — Claude 초안 v2 (2026-10-02)",
                  "# 프레스 유압펌프 과제 재설계 계획 — 초안 v2 (2026-10-02)")
    t = re.sub(r"\n작성: Claude Code \(Opus 5\.5\)\. 위치: `[^`]+`\. v1\(커밋 3eb49a1\)을 독립 검토 3종으로 고친 판이다\.\n",
               "\nv1을 독립 검토 3종으로 고친 판이다.\n", t)
    t = re.sub(r"\n\| 코덱스 계획과의 병합 \| [^\n]*", "", t)
    # drop section 6 (comparison checklist written in advance)
    t = re.sub(r"\n## 6\. 코덱스 계획과 비교할 때 볼 점.*?(?=\n## 7\.)", "\n", t, flags=re.S)
    t = t.replace("## 7. 독립성과 리서치 방법", "## 6. 리서치 방법")
    t = re.sub(r"\n- 코덱스 초안\([^\n]*", "", t)
    t = t.replace("| `reviews/` | 독립 검토 원문 3종(방법론, 현장, 전략) |", "| `reviews/` | 독립 검토 원문 3종(이 사본에는 없음) |")
    t = t.replace("| `sources/` | 리서치 에이전트 원보고서 R1–R9 |", "| `sources/` | 리서치 원보고서 R1–R9(이 사본에는 없음) |")
    t = t.replace("| `06_review_response.md` | 독립 검토 3종의 P0/P1 지적별 처리 결과 |", "| `06_review_response.md` | 독립 검토 처리 결과(이 사본에는 없음) |")
    return t

def sanitize_generic(t):
    t = t.replace("Claude Code", "계획 작성자").replace("(Claude)", "(계획자)").replace("Claude", "계획자")
    return t

def build(dst, label_claude, label_codex):
    for lab in (label_claude, label_codex):
        (dst / lab).mkdir(parents=True, exist_ok=True)
    # Claude plan main docs
    for f in ["README.md", "01_data_diagnosis.md", "02_research_sources.md", "03_approach_options.md",
              "04_evaluation_protocol.md", "05_execution_plan.md"]:
        t = (CL / f).read_text(encoding="utf-8")
        if f == "README.md":
            t = sanitize_claude_readme(t)
        t = sanitize_generic(t)
        (dst / label_claude / f).write_text(t, encoding="utf-8")
    (dst / label_claude / "eda").mkdir(exist_ok=True)
    for p in (CL / "eda").iterdir():
        if p.suffix in (".py", ".txt", ".json"):
            shutil.copy2(p, dst / label_claude / "eda" / p.name)
    # Codex plan docs (no identity markers found)
    for p in CX.glob("*.md"):
        shutil.copy2(p, dst / label_codex / p.name)

build(SP / "blind_judge1", "plan_X", "plan_Y")   # judge 1: Claude = X
build(SP / "blind_judge2", "plan_Y", "plan_X")   # judge 2: Claude = Y
print("ok")
