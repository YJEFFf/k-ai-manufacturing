"""복사 보고서를 한컴 양식 HWPX와 PDF로 저장한다(Windows COM, pyhwpx).

claude/report/build_hwpx.py에서 복사한 작업용 빌더. 원본은 읽기만 한다.
실행: python build_hwpx_copy.py --check-only 또는 python build_hwpx_copy.py
- 입력/그림/출력은 기본적으로 yejun의 복사 보고서 폴더를 사용한다
- 출력은 yejun 아래로 제한하고 보호 원본의 해시를 조립 전후 확인한다
- 서식은 양식의 예시 문단(◦ 휴먼명조 14 / - 휴먼명조 14 / * 휴먼명조 10)에서 읽어 그대로 쓴다
- 작성 요령 표 6개·예시 문단·안내 문단은 지우고, 만족도 조사 캡처 칸(필수)은 남겨 새 쪽에서 시작하게 한다
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
COPY_DIR = REPO / "yejun/결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08"
TEMPLATE_NAME = "경진대회 결과보고서 양식_일반국민,대학(원)생 부문.hwpx"
TEMPLATE = REPO / "관련 자료" / TEMPLATE_NAME
SRC = COPY_DIR / "결과보고서_북적북적_개선본.md"
OUT = SRC.with_suffix(".hwpx")
FIGURE_DIR = COPY_DIR / "figures"
# v5 본문 등장 순서의 그림 번호 → 파일
FIGS = {1: "fig1_structure.png", 2: "fig8_observability.png", 3: "fig0_leak.png", 4: "fig2_collection.png",
        5: "fig9_regime_timeline.png", 6: "fig3_flow.png", 7: "fig10_load_vibration.png", 8: "fig11_model_structure.png",
        9: "fig5_models.png", 10: "fig4_miss_position.png", 11: "fig6_rules.png", 12: "fig13_stage_timeline.png", 13: "fig12_alarm_card.png", 14: "fig7_console.png"}
FIG_WIDTH_MM = 150
# 내어쓰기(실측: 0.005pt/단위, 문단 왼쪽 56.6pt). 둘째 줄이 기호 뒤 첫 글자와 맞도록 PDF에서 잰 값
DASH_INDENT = -7020    # "   - " 14pt (양식 값 -7720은 3.5pt 어긋남)
DOT_INDENT = -9800     # "     ·" 14pt (· 는 전각)
STAR_INDENT = -8960    # "       * " 10pt
SUBMIT_DATE = "2026년  10월  8일"
LEADER, MEMBER = "허예준", "장준용"
# 양식 예시 문단에서 옮겨 올 문단 모양·글자 모양 항목
PARA_KEYS = ("AlignType", "LeftMargin", "RightMargin", "Indentation", "LineSpacing", "LineSpacingType", "PrevSpacing", "NextSpacing")
CHAR_KEYS = ("FaceNameHangul", "FaceNameLatin", "FaceNameHanja", "FaceNameJapanese", "FaceNameOther", "FaceNameSymbol", "FaceNameUser",
             "FontTypeHangul", "FontTypeLatin", "Height", "Bold", "TextColor")
PIPE = "│"   # 표 칸 안의 \| 를 칸 나누기와 헷갈리지 않게 잠시 바꿔 두는 문자


def verify_protected_sources():
    """바이너리는 그대로, Git text는 CRLF를 LF로 정규화해 Mac 해시와 비교한다."""
    manifest = json.loads((HERE / "source_manifest.json").read_text(encoding="utf-8"))
    rows = []
    for relative, expected in manifest["protected_files"].items():
        path = REPO / relative
        data = path.read_bytes()
        raw = hashlib.sha256(data).hexdigest()
        canonical = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() if path.suffix == ".md" else raw
        if canonical != expected:
            raise ValueError(f"Protected original changed: {relative}")
        rows.append({"path": relative, "sha256": raw, "canonical_sha256": canonical,
                     "crlf_only_difference": raw != canonical})
    return rows


def configure():
    global SRC, OUT, TEMPLATE, FIGURE_DIR, FIGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SRC)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    parser.add_argument("--figures", type=Path)
    parser.add_argument("--figure-map", type=Path,
                        default=HERE / "figure_map.json" if (HERE / "figure_map.json").is_file() else None,
                        help="JSON figure-number mapping; uses this folder's figure_map.json when available")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    SRC = args.source.resolve()
    OUT = (args.output or SRC.with_suffix(".hwpx")).resolve()
    TEMPLATE = args.template.resolve()
    FIGURE_DIR = (args.figures or SRC.parent / "figures").resolve()
    allowed = (REPO / "yejun").resolve()
    for path in (SRC, OUT):
        if not path.is_relative_to(allowed) or "원본보관" in path.parts:
            raise ValueError(f"Working source/output must be under yejun/ and outside 원본보관: {path}")
    if OUT.suffix.lower() != ".hwpx":
        raise ValueError("Output must have .hwpx extension")
    if args.figure_map:
        FIGS = {**FIGS, **{int(k): v for k, v in json.loads(args.figure_map.read_text(encoding="utf-8")).items()}}
    protected = verify_protected_sources()
    if not TEMPLATE.is_file():
        raise FileNotFoundError(TEMPLATE)
    cover, chapters = parse(SRC.read_text(encoding="utf-8-sig"))
    figures = [b[1] for _, blocks in chapters for b in blocks if b[0] == "fig"]
    for number in figures:
        if number not in FIGS:
            raise ValueError(f"Figure {number} needs an entry in --figure-map")
        path = (FIGURE_DIR / FIGS[number]).resolve()
        if not path.is_relative_to(FIGURE_DIR) or not path.is_file():
            raise FileNotFoundError(path)
    return args, {"source": str(SRC), "output": str(OUT), "template": str(TEMPLATE),
                  "chapters": len(chapters), "figures": len(figures), "protected_sources": protected}


def clean(text: str) -> str:
    """md 꾸밈(**, `, \\|)을 걷어 내고 곧은 따옴표를 둥근 따옴표로 바꾼다."""
    text = text.replace("**", "").replace("`", "").replace(PIPE, "|").replace("\\|", "|")
    text = re.sub(r'"([^"]*)"', "“\\1”", text)   # 한글 자동 고침이 따옴표 방향을 바꾸지 않게 둥근 따옴표로
    text = re.sub(r"'([^']*)'", "‘\\1’", text)
    return text.strip()


def parse(md: str):
    """md → (표지 정보, [(장 제목 일부, [블록])]). 블록: ("p", 단계, 글) / ("table", 행들) / ("fig", 번호, 설명)"""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    if md.startswith("---"):       # 머리말(front matter) 제외
        md = md.split("---", 2)[2]
    sections = re.split(r"(?m)^# ", md)
    cover, chapters = {"summary": []}, []
    for sec in sections:
        if not sec.strip():
            continue
        title, _, body = sec.partition("\n")
        lines = body.splitlines()
        if title.startswith("표지"):     # 표지 장은 프로젝트명·요약만 뽑아 표지 표에 넣는다
            for ln in lines:
                if ln.startswith("- 프로젝트명:"):
                    cover["project"] = clean(ln.split(":", 1)[1])
                elif ln.lstrip().startswith("◦"):
                    cover["summary"].append(clean(ln.lstrip()[1:]))
            continue
        heading = re.sub(r"^□\s*", "", title).split("〔")[0].strip()   # 양식에서 찾을 장 제목(□ 와 〔배점〕 제외)
        blocks, table = [], []
        base = 0   # "## ◦" 소절 아래에서는 들여쓰기 0의 "- "가 - 단계, 맨 "◦" 항목 아래에서는 들여쓰기 2가 - 단계
        for ln in lines + [""]:
            s = ln.strip()
            if s.startswith("|"):
                table.append([clean(c) for c in s.replace("\\|", PIPE).strip("|").split("|")])
                continue
            if table:   # 표가 끝난 줄: 구분선(---) 행을 빼고 블록으로 넘긴다
                rows = [r for r in table if not all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in r)]
                blocks.append(("table", rows)); table = []
            if not s or s.startswith("※ 경진대회 만족도"):
                continue
            m = re.fullmatch(r"\[그림 (\d+): (.*)\]", s)
            if m:
                blocks.append(("fig", int(m.group(1)), clean(m.group(2)))); continue
            indent = len(ln) - len(ln.lstrip())
            if s.startswith("## "):
                blocks.append(("p", "h", clean(s[3:].lstrip("◦ ").strip()))); base = 0
            elif s.startswith("◦"):
                blocks.append(("p", "o", clean(s[1:]))); base = 1
            elif s.startswith(("- ", "* ")):
                level = "-" if indent // 2 - base <= 0 else ("*" if s.startswith("* ") else "·")
                blocks.append(("p", level, clean(s[2:])))
            else:
                blocks.append(("p", "-", clean(s)))
        chapters.append((heading, blocks))
    return cover, chapters


def main():
    args, preflight = configure()
    if args.check_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return
    # pyhwpx 1.7.2 locates its bundled security DLL through `pip show pyhwpx`.
    # Ensure that command uses this interpreter's installed environment.
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    from pyhwpx import Hwp
    source_before = hashlib.sha256(SRC.read_bytes()).hexdigest()
    cover, chapters = parse(SRC.read_text(encoding="utf-8-sig"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATE, OUT)
    print("한컴 양식 조립 시작:", OUT, flush=True)
    hwp = Hwp(new=True, visible=False)
    try:
        hwp.set_message_box_mode(0x10000)   # 예/아니오 확인 창에 자동으로 "예"를 눌러 멈추지 않게
        if not hwp.open(str(OUT)):
            raise RuntimeError(f"Hancom could not open the template copy: {OUT}")

        # 1) 양식 예시 문단에서 서식 읽기
        styles = {}
        for key, text in (("o", "◦ 휴먼명조 14"), ("-", "- 휴먼명조 14"), ("*", "* 휴먼명조 10")):
            hwp.MoveDocBegin(); assert hwp.find(text), text
            hwp.MoveParaBegin(); hwp.MoveParaEnd(); hwp.MoveLeft(); hwp.MoveLeft()   # 문단 끝 표시가 아닌 글자 위에서 모양을 읽는다
            para = {k: v for k, v in hwp.get_parashape_as_dict().items() if k in PARA_KEYS and v is not None}
            char = {k: v for k, v in hwp.get_charshape_as_dict().items() if k in CHAR_KEYS and v is not None}
            styles[key] = (para, char)
        styles["*"] = ({**styles["*"][0], "Indentation": STAR_INDENT}, styles["*"][1])   # 양식 값(-6084)은 "       * " 폭보다 좁아 둘째 줄이 기호 왼쪽으로 나간다
        styles["-"] = ({**styles["-"][0], "Indentation": DASH_INDENT}, styles["-"][1])
        styles["·"] = ({**styles["-"][0], "Indentation": DOT_INDENT}, styles["-"][1])   # 하위 본문 항목: 양식 - 단계와 같은 14pt, 한 단계 깊게
        # 소절 제목과 그림은 "다음 문단과 함께": 제목만, 또는 그림만 쪽 끝에 남지 않게 한다
        styles["h"] = ({**styles["o"][0], "KeepWithNext": 1}, {**styles["o"][1], "Bold": 1})
        styles["cap"] = ({**styles["*"][0], "AlignType": 3, "Indentation": 0, "KeepLinesTogether": 1}, styles["*"][1])   # 그림 설명은 같은 쪽에 유지
        styles["center"] = ({**styles["cap"][0], "KeepWithNext": 1}, styles["cap"][1])
        # 표 칸·표지: 양식에 예시가 없어 직접 정한다(Height는 1/100pt 단위, 1000 = 10pt)
        styles["cell"] = ({"AlignType": 1, "LeftMargin": 0, "Indentation": 0, "LineSpacing": 130, "LineSpacingType": 0,
                           "PrevSpacing": 0, "NextSpacing": 0}, {**styles["*"][1], "Height": 1000})
        styles["cellh"] = ({**styles["cell"][0], "AlignType": 3}, {**styles["cell"][1], "Bold": 1})
        styles["covername"] = ({**styles["cell"][0], "AlignType": 1}, {**styles["o"][1], "Height": 1200, "Bold": 1})
        styles["coverteam"] = ({**styles["cell"][0], "AlignType": 1}, {**styles["o"][1], "Height": 1200})
        styles["cover"] = ({"AlignType": 1, "LeftMargin": 0, "Indentation": -1800, "LineSpacing": 150, "LineSpacingType": 0,
                            "PrevSpacing": 0, "NextSpacing": 300}, {**styles["o"][1], "Height": 1100})

        def apply(name):
            """styles[name]의 문단·글자 모양을 커서 위치에 건다. 기울임은 늘 끈다."""
            para, char = styles[name]
            ps = hwp.HParameterSet.HParaShape
            hwp.HAction.GetDefault("ParagraphShape", ps.HSet)
            for k, v in {"KeepWithNext": 0, "KeepLinesTogether": 0, **para}.items():
                ps.HSet.SetItem(k, v)
            hwp.HAction.Execute("ParagraphShape", ps.HSet)
            cs = hwp.HParameterSet.HCharShape
            hwp.HAction.GetDefault("CharShape", cs.HSet)
            for k, v in {"Italic": 0, **char}.items():
                cs.HSet.SetItem(k, v)
            hwp.HAction.Execute("CharShape", cs.HSet)

        # 2) 작성 요령 표 삭제(표지 표·설문 예시 표는 남김). 표 하나를 지우면 순번이 당겨지므로 매번 처음부터 다시 찾는다
        deleted = 0
        for _ in range(10):
            tables = [c for c in hwp.ctrl_list if c.CtrlID == "tbl"]
            target = None
            for idx in range(len(tables)):
                hwp.get_into_nth_table(idx); hwp.MoveSelListEnd(); first = hwp.get_selected_text(); hwp.HAction.Run("Cancel")   # 첫 칸 글자
                if first.strip().startswith("작성 요령"):
                    target = idx
                    break
            if target is None:
                break
            hwp.delete_ctrl([c for c in hwp.ctrl_list if c.CtrlID == "tbl"][target]); deleted += 1
        print("작성 요령 표 삭제:", deleted, flush=True)
        # 3) 예시 문단·안내 문단 삭제(같은 글이 여러 번 나와 없어질 때까지 반복)
        for text in ("휴먼명조 14, 줄간격 160", "휴먼명조 10, 줄간격 160", "추가적으로 기술할 내용은 자유롭게 작성 가능", "※ 작성 후 삭제", "작성 요령"):
            for _ in range(20):
                hwp.MoveDocBegin()
                if not hwp.find(text):
                    break
                hwp.MoveParaBegin(); hwp.MoveSelNextParaBegin(); hwp.HAction.Run("Delete")

        # 3b) 작성 요령 표를 지운 자리의 빈 문단 정리(장 사이 큰 공백 제거). 앞 문단 끝의 문단 나눔을 지워 제목 서식은 건드리지 않는다
        def selected_para_text():
            """커서가 있는 문단의 글자. 읽은 뒤 선택을 풀어 다음 이동에 영향이 없게 한다."""
            hwp.MoveParaBegin(); hwp.MoveSelParaEnd()
            try:
                return hwp.get_selected_text() or ""
            finally:
                hwp.HAction.Run("Cancel")
        for heading, _ in chapters[1:]:
            for _ in range(10):
                hwp.MoveDocBegin(); assert hwp.find(heading), heading
                hwp.HAction.Run("Cancel"); hwp.MoveParaBegin(); hwp.HAction.Run("MovePrevParaBegin")
                if selected_para_text().strip():
                    break
                hwp.MoveParaBegin(); hwp.MoveLeft(); hwp.HAction.Run("MoveSelRight"); hwp.HAction.Run("Delete")
        # 3c) 양식에서 제3장·제4장 제목만 □ 가 빠져 있어 맞춘다
        for heading, _ in chapters:
            hwp.MoveDocBegin(); assert hwp.find(heading), heading
            hwp.HAction.Run("Cancel")
            if not selected_para_text().lstrip().startswith("□"):
                hwp.MoveParaBegin(); hwp.insert_text("□ ")

        # 4) 표지
        def fill_right_of(label, lines, style):
            """표지 표에서 label 칸의 오른쪽 칸에 lines를 문단으로 채운다."""
            hwp.MoveDocBegin(); assert hwp.find(label), label
            hwp.HAction.Run("Cancel"); hwp.HAction.Run("TableRightCell")
            for i, ln in enumerate(lines):
                apply(style); hwp.insert_text(ln)
                if i < len(lines) - 1:
                    hwp.BreakPara()
            hwp.HAction.Run("Cancel")
        fill_right_of("프로젝트명", [cover["project"]], "covername")
        fill_right_of("팀명", ["북적북적"], "coverteam")
        fill_right_of("내용요약", ["◦ " + s for s in cover["summary"]], "cover")

        def retype_para(find_text, fn):
            """find_text가 든 문단 글을 fn으로 바꿔 다시 쓴다(제출일·서명란)."""
            hwp.MoveDocBegin(); assert hwp.find(find_text), find_text
            hwp.HAction.Run("Cancel")
            hwp.MoveParaBegin(); hwp.MoveSelParaEnd()
            old = hwp.get_selected_text()          # 이 호출이 선택을 풀어 버려 지우기 전에 다시 선택한다
            new = fn(old)
            assert new != old, find_text
            hwp.MoveParaBegin(); hwp.MoveSelParaEnd(); hwp.HAction.Run("Delete")
            hwp.insert_text(new)
        retype_para("2026년", lambda s: re.sub(r"2026년\s+월\s+일", SUBMIT_DATE, s))
        # 이름 길이만큼 공백을 줄여 (서명) 위치를 유지한다
        retype_para("팀장 :", lambda s: re.sub(r"팀장 :(\s+)\(서명\)", lambda m: f"팀장 :  {LEADER}" + " " * max(len(m.group(1)) - 8, 3) + "(서명)", s))
        retype_para("팀원 :", lambda s: re.sub(r"팀원 :(\s+)\(서명\)", lambda m: f"팀원 :  {MEMBER}" + " " * max(len(m.group(1)) - 8, 3) + "(서명)", s, count=1))
        # 팀원이 1명이라 비어 있는 둘째 팀원 줄은 지운다
        hwp.MoveDocBegin()
        if hwp.find("팀원 :                 (서명)"):
            hwp.HAction.Run("Cancel"); hwp.MoveParaBegin(); hwp.MoveSelNextParaBegin(); hwp.HAction.Run("Delete")

        # 5) 장별 본문: 장 제목 문단 뒤에 블록을 차례로 넣는다. 본문 폭 = 용지 폭 - 좌우 여백 - 제본 여백 - 2mm
        sd = hwp.HParameterSet.HSecDef
        hwp.HAction.GetDefault("PageSetup", sd.HSet)
        text_width = (sd.PageDef.PaperWidth - sd.PageDef.LeftMargin - sd.PageDef.RightMargin
                      - sd.PageDef.GutterLen - hwp.MiliToHwpUnit(2))

        def col_widths(rows, ncol):
            """열 너비 = 내용 길이(머리 칸과 본문 평균 중 큰 값)의 제곱근에 비례. 칸 안쪽 여백 1.8mm×2를 뺀다"""
            weights = []
            for j in range(ncol):
                body = [len(r[j]) for r in rows[1:] if j < len(r) and r[j]]
                weights.append(max(len(rows[0][j]) if j < len(rows[0]) else 1, sum(body) / max(len(body), 1)) ** 0.5)
            usable = text_width - hwp.MiliToHwpUnit(3.6 * ncol)
            return [round(usable * w / sum(weights)) for w in weights]

        marker = {"o": " ◦ ", "h": " ◦ ", "-": "   - ", "·": "     ·", "*": "       * "}   # 양식 예시와 같은 기호·앞 공백
        for heading, blocks in chapters:
            print("본문 삽입:", heading, flush=True)
            hwp.MoveDocBegin(); assert hwp.find(heading), heading
            hwp.MoveParaEnd(); hwp.BreakPara()
            for i, b in enumerate(blocks):
                # 소절 제목(장 첫 소절 제외)과 보조 참고문헌 앞은 한 줄 띄운다
                if i > 0 and b[0] == "p" and (b[1] == "h" or b[2].startswith("보조 참고문헌")):
                    apply("o"); hwp.BreakPara()
                if b[0] == "p":
                    apply(b[1]); hwp.insert_text(marker[b[1]] + b[2]); hwp.BreakPara()
                elif b[0] == "table":
                    rows = b[1]; ncol = max(len(r) for r in rows)
                    apply("cell")
                    ps = hwp.HParameterSet.HTableCreation
                    hwp.HAction.GetDefault("TableCreate", ps.HSet)
                    ps.Rows, ps.Cols, ps.WidthType, ps.HeightType = len(rows), ncol, 2, 0   # 너비 직접 지정, 높이 자동
                    ps.WidthValue = text_width
                    ps.CreateItemArray("ColWidth", ncol)
                    for j, wj in enumerate(col_widths(rows, ncol)):
                        ps.ColWidth.SetItem(j, wj)
                    ps.TableProperties.Width = text_width
                    hwp.HAction.Execute("TableCreate", ps.HSet)
                    tp = hwp.CreateSet("Table"); tp.SetItem("TreatAsChar", 1)   # 글자처럼 취급: 표가 본문 순서대로 놓이고 남은 자리가 모자라면 표째 다음 쪽으로(한 쪽보다 긴 표는 잘리므로 layout_check로 확인)
                    tp.SetItem("OutsideMarginTop", hwp.MiliToHwpUnit(1)); tp.SetItem("OutsideMarginBottom", hwp.MiliToHwpUnit(3))
                    hwp.ParentCtrl.Properties = tp
                    # 머리 행(첫 행)을 블록으로 잡아 회색으로 칠한 뒤 첫 칸으로 돌아와 칸마다 글을 넣는다
                    hwp.HAction.Run("TableCellBlock"); hwp.HAction.Run("TableCellBlockExtend"); hwp.HAction.Run("TableColEnd")
                    hwp.cell_fill((230, 230, 230))
                    hwp.HAction.Run("TableColBegin")
                    for i, r in enumerate(rows):
                        for j in range(ncol):
                            apply("cellh" if i == 0 else "cell")
                            hwp.insert_text(r[j] if j < len(r) else "")
                            if not (i == len(rows) - 1 and j == ncol - 1):
                                hwp.HAction.Run("TableRightCell")
                    hwp.MoveParentList(); hwp.MoveParaEnd(); hwp.BreakPara()   # 표 밖으로 나와 다음 문단
                elif b[0] == "fig":
                    n, cap = b[1], b[2]
                    path = FIGURE_DIR / FIGS[n]
                    w, h = Image.open(path).size
                    apply("center")
                    hwp.insert_picture(str(path), sizeoption=1, width=FIG_WIDTH_MM, height=round(FIG_WIDTH_MM * h / w))   # 폭 150mm, 비율 유지
                    hwp.BreakPara()
                    apply("cap"); hwp.insert_text(f"[그림 {n}] {cap}"); hwp.BreakPara()
        if not hwp.save_as(str(OUT), "HWPX"):
            raise RuntimeError(f"Hancom could not save HWPX: {OUT}")
    finally:
        hwp.quit()
    patch_hwpx(OUT)
    # XML을 고친 hwpx를 다시 열어 PDF를 뽑는다(쪽 나눔이 PDF에도 반영되도록)
    h2 = Hwp(new=True, visible=False)   # 방금 끝낸 인스턴스가 실행 목록에 남아 붙으면 COM 오류가 나므로 새로 띄운다
    try:
        h2.set_message_box_mode(0x10000)
        if not h2.open(str(OUT)):
            raise RuntimeError(f"Hancom could not reopen HWPX: {OUT}")
        if not h2.save_as(str(OUT.with_suffix(".pdf")), "PDF"):
            raise RuntimeError(f"Hancom could not export PDF: {OUT.with_suffix('.pdf')}")
    finally:
        h2.quit()
    verify_protected_sources()
    if hashlib.sha256(SRC.read_bytes()).hexdigest() != source_before:
        raise RuntimeError("Source changed during Hancom rendering; rebuild after the manuscript is final")
    print("저장:", OUT.name, OUT.with_suffix(".pdf").name)


def survey_on_new_page(x: str) -> tuple[str, int]:
    """만족도 조사 제목 문단을 새 쪽에서 시작하게 한다. 반환: (고친 XML, 지운 문단 수)"""
    return new_page_at(x, x.index("경진대회 만족도 조사 완료"))


def new_page_at(x: str, pos: int) -> tuple[str, int]:
    """pos가 든 문단 바로 앞의 빈 문단을 지우고, 그 문단에 쪽 나눔(pageBreak="1")을 건다.
    빈 문단이 앞 쪽에 남아 쪽 나눔 앞에 빈 쪽을 만드는 것을 막는다. 빈 문단 = 글자도 표·그림·컨트롤도 없는 <hp:p>"""
    head = x.rfind("<hp:p ", 0, pos)   # 그 문단의 여는 태그 위치
    removed = 0
    while x[:head].endswith("</hp:p>"):      # 바로 앞 문단이 비어 있는 동안 하나씩 지운다
        start = x.rfind("<hp:p ", 0, head)
        para = x[start:head]
        texts = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", para, flags=re.S))
        if texts.strip() or re.search(r"<hp:(tbl|pic|rect|container|ctrl|secPr)", para):
            break
        x = x[:start] + x[head:]
        head = start
        removed += 1
    tag_end = x.index(">", head)
    return x[:head] + re.sub(r'pageBreak="\d"', 'pageBreak="1"', x[head:tag_end]) + x[tag_end:], removed


# 장 제목과 참고문헌은 새 쪽에서 시작한다(10/5 한글에서 빈 줄로 맞춘 배치를 쪽 나눔으로 옮김. 빈 줄은 글이 바뀌면 어긋난다)
NEW_PAGE = [f"제{n}장." for n in range(1, 7)] + ["주요 참고문헌"]


def break_before(x: str, text: str) -> str:
    """text가 든 문단을 새 쪽에서 시작하게 한다(바로 앞 빈 문단은 지움)."""
    assert x.count(text) == 1, text
    return new_page_at(x, x.index(text))[0]


def patch_hwpx(path: Path):
    """hwpx(zip) 안 XML을 직접 고친다: 마지막 저장자(PC 사용자 이름)를 비우고, 각 장·참고문헌·만족도 조사를 새 쪽에서 시작하게 한다.
    항목 순서·압축 방식은 원래 ZipInfo 그대로 둔다(mimetype 먼저, 무압축)."""
    with zipfile.ZipFile(path) as z:
        infos = z.infolist(); data = {i.filename: z.read(i.filename) for i in infos}
    data["Contents/content.hpf"] = re.sub(rb'(<opf:meta name="lastsaveby" content="text">)[^<]*(</opf:meta>)', rb"\1\2",
                                          data["Contents/content.hpf"])
    x, removed = survey_on_new_page(data["Contents/section0.xml"].decode("utf-8"))
    for text in NEW_PAGE:
        x = break_before(x, text)
    # 표는 쪽 경계에서 나누지 않는다(남은 자리가 모자라면 표째 다음 쪽으로)
    x = re.sub(r'(<hp:tbl [^>]*?)pageBreak="CELL"', r'\1pageBreak="NONE"', x)
    x = re.sub("—(?=[a-z])", "--", x)    # 한글 자동 고침이 명령 옵션 --quick 의 -- 를 긴 줄표로 바꾼 것을 되돌린다
    x = re.sub("(?<= )–(?=[a-z])", "-", x)   # 같은 이유로 pip install -r, conda env create -f 의 - 가 반각 줄표(–)로 바뀐 것
    data["Contents/section0.xml"] = x.encode("utf-8")
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as dst:
        for info in infos:
            dst.writestr(info, data[info.filename])
    tmp.replace(path)
    print("만족도 조사 앞 빈 문단 삭제", removed)


if __name__ == "__main__":
    main()
