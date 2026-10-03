"""final.md → 주최 측 양식(hwpx)에 조립하고 PDF로 저장한다(한컴 2022 COM, pyhwpx).

- 양식의 예시 문단(◦ 휴먼명조 14 / - 휴먼명조 14 / * 휴먼명조 10)에서 문단·글자 모양을 읽어 본문에 그대로 쓴다
- 작성 요령 표 6개, 예시 문단, "추가적으로 기술할 내용" 안내 문단을 지운다. 만족도 조사 캡처 칸(필수)은 남긴다
- 출력: report/결과보고서_북적북적.hwpx, report/결과보고서_북적북적.pdf
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "00_공고_양식" / "경진대회 결과보고서 양식_일반국민,대학(원)생 부문.hwpx"
SRC = HERE / (sys.argv[1] if len(sys.argv) > 1 else "final.md")
OUT = HERE / (sys.argv[2] if len(sys.argv) > 2 else "결과보고서_북적북적.hwpx")
# v5 본문 등장 순서의 그림 번호 → 파일
FIGS = {1: "fig1_structure.png", 2: "fig8_observability.png", 3: "fig0_leak.png", 4: "fig2_collection.png",
        5: "fig9_regime_timeline.png", 6: "fig3_flow.png", 7: "fig10_load_vibration.png", 8: "fig5_models.png",
        9: "fig4_miss_position.png", 10: "fig6_rules.png", 11: "fig7_console.png"}
FIG_WIDTH_MM = 150
# 내어쓰기(실측: 0.005pt/단위, 문단 왼쪽 56.6pt). 둘째 줄이 기호 뒤 첫 글자와 맞도록 PDF에서 잰 값
DASH_INDENT = -7020    # "   - " 14pt (양식 값 -7720은 3.5pt 어긋남)
DOT_INDENT = -9800     # "     ·" 14pt (· 는 전각)
STAR_INDENT = -8960    # "       * " 10pt
SUBMIT_DATE = "2026년  10월  8일"
LEADER, MEMBER = "허예준", "장준용"
PARA_KEYS = ("AlignType", "LeftMargin", "RightMargin", "Indentation", "LineSpacing", "LineSpacingType", "PrevSpacing", "NextSpacing")
CHAR_KEYS = ("FaceNameHangul", "FaceNameLatin", "FaceNameHanja", "FaceNameJapanese", "FaceNameOther", "FaceNameSymbol", "FaceNameUser",
             "FontTypeHangul", "FontTypeLatin", "Height", "Bold", "TextColor")


PIPE = "│"   # 표 칸 안의 \| 를 잠시 바꿔 두는 문자


def clean(text: str) -> str:
    text = text.replace("**", "").replace("`", "").replace(PIPE, "|").replace("\\|", "|")
    text = re.sub(r'"([^"]*)"', "“\\1”", text)   # 한글 자동 고침이 따옴표 방향을 바꾸지 않게 둥근 따옴표로
    text = re.sub(r"'([^']*)'", "‘\\1’", text)
    return text.strip()


def parse(md: str):
    """md → (표지 정보, [(장 제목 일부, [블록])]). 블록: ("p", 단계, 글) / ("table", 행들) / ("fig", 번호, 설명)"""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    if md.startswith("---"):
        md = md.split("---", 2)[2]
    sections = re.split(r"(?m)^# ", md)
    cover, chapters = {"summary": []}, []
    for sec in sections:
        if not sec.strip():
            continue
        title, _, body = sec.partition("\n")
        lines = body.splitlines()
        if title.startswith("표지"):
            for ln in lines:
                if ln.startswith("- 프로젝트명:"):
                    cover["project"] = clean(ln.split(":", 1)[1])
                elif ln.lstrip().startswith("◦"):
                    cover["summary"].append(clean(ln.lstrip()[1:]))
            continue
        heading = re.sub(r"^□\s*", "", title).split("〔")[0].strip()
        blocks, table = [], []
        base = 0   # "## ◦" 소절 아래에서는 들여쓰기 0의 "- "가 - 단계, 맨 "◦" 항목 아래에서는 들여쓰기 2가 - 단계
        for ln in lines + [""]:
            s = ln.strip()
            if s.startswith("|"):
                table.append([clean(c) for c in s.replace("\\|", PIPE).strip("|").split("|")])
                continue
            if table:
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
    cover, chapters = parse(SRC.read_text(encoding="utf-8"))
    shutil.copy(TEMPLATE, OUT)
    from pyhwpx import Hwp
    hwp = Hwp(visible=False)
    try:
        hwp.set_message_box_mode(0x10000)
        hwp.open(str(OUT))

        # 1) 양식 예시 문단에서 서식 읽기
        styles = {}
        for key, text in (("o", "◦ 휴먼명조 14"), ("-", "- 휴먼명조 14"), ("*", "* 휴먼명조 10")):
            hwp.MoveDocBegin(); assert hwp.find(text), text
            hwp.MoveParaBegin(); hwp.MoveParaEnd(); hwp.MoveLeft(); hwp.MoveLeft()
            para = {k: v for k, v in hwp.get_parashape_as_dict().items() if k in PARA_KEYS and v is not None}
            char = {k: v for k, v in hwp.get_charshape_as_dict().items() if k in CHAR_KEYS and v is not None}
            styles[key] = (para, char)
        styles["*"] = ({**styles["*"][0], "Indentation": STAR_INDENT}, styles["*"][1])   # 양식 값(-6084)은 "       * " 폭보다 좁아 둘째 줄이 기호 왼쪽으로 나간다
        styles["-"] = ({**styles["-"][0], "Indentation": DASH_INDENT}, styles["-"][1])
        styles["·"] = ({**styles["-"][0], "Indentation": DOT_INDENT}, styles["-"][1])   # 하위 본문 항목: 양식 - 단계와 같은 14pt, 한 단계 깊게
        styles["h"] = (styles["o"][0], {**styles["o"][1], "Bold": 1})
        styles["cap"] = ({**styles["*"][0], "AlignType": 3, "Indentation": 0}, styles["*"][1])
        styles["center"] = ({**styles["*"][0], "AlignType": 3, "Indentation": 0}, styles["*"][1])
        styles["cell"] = ({"AlignType": 1, "LeftMargin": 0, "Indentation": 0, "LineSpacing": 130, "LineSpacingType": 0,
                           "PrevSpacing": 0, "NextSpacing": 0}, {**styles["*"][1], "Height": 1000})
        styles["cellh"] = ({**styles["cell"][0], "AlignType": 3}, {**styles["cell"][1], "Bold": 1})
        styles["covername"] = ({**styles["cell"][0], "AlignType": 1}, {**styles["o"][1], "Height": 1200, "Bold": 1})
        styles["coverteam"] = ({**styles["cell"][0], "AlignType": 1}, {**styles["o"][1], "Height": 1200})
        styles["cover"] = ({"AlignType": 1, "LeftMargin": 0, "Indentation": -1800, "LineSpacing": 150, "LineSpacingType": 0,
                            "PrevSpacing": 0, "NextSpacing": 300}, {**styles["o"][1], "Height": 1100})

        def apply(name):
            para, char = styles[name]
            ps = hwp.HParameterSet.HParaShape
            hwp.HAction.GetDefault("ParagraphShape", ps.HSet)
            for k, v in para.items():
                ps.HSet.SetItem(k, v)
            hwp.HAction.Execute("ParagraphShape", ps.HSet)
            cs = hwp.HParameterSet.HCharShape
            hwp.HAction.GetDefault("CharShape", cs.HSet)
            for k, v in {"Italic": 0, **char}.items():
                cs.HSet.SetItem(k, v)
            hwp.HAction.Execute("CharShape", cs.HSet)

        # 2) 작성 요령 표 삭제(표지 표·설문 예시 표는 남김)
        deleted = 0
        for _ in range(10):
            tables = [c for c in hwp.ctrl_list if c.CtrlID == "tbl"]
            target = None
            for idx in range(len(tables)):
                hwp.get_into_nth_table(idx); hwp.MoveSelListEnd(); first = hwp.get_selected_text(); hwp.HAction.Run("Cancel")
                if first.strip().startswith("작성 요령"):
                    target = idx
                    break
            if target is None:
                break
            hwp.delete_ctrl([c for c in hwp.ctrl_list if c.CtrlID == "tbl"][target]); deleted += 1
        print("작성 요령 표 삭제:", deleted)
        # 3) 예시 문단·안내 문단 삭제
        for text in ("휴먼명조 14, 줄간격 160", "휴먼명조 10, 줄간격 160", "추가적으로 기술할 내용은 자유롭게 작성 가능", "※ 작성 후 삭제", "작성 요령"):
            for _ in range(20):
                hwp.MoveDocBegin()
                if not hwp.find(text):
                    break
                hwp.MoveParaBegin(); hwp.MoveSelNextParaBegin(); hwp.HAction.Run("Delete")

        # 3b) 작성 요령 표를 지운 자리의 빈 문단 정리(장 사이 큰 공백 제거). 앞 문단 끝의 문단 나눔을 지워 제목 서식은 건드리지 않는다
        def selected_para_text():
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
            hwp.MoveDocBegin(); assert hwp.find(find_text), find_text
            hwp.HAction.Run("Cancel")
            hwp.MoveParaBegin(); hwp.MoveSelParaEnd()
            old = hwp.get_selected_text()          # 이 호출이 선택을 푼다
            new = fn(old)
            assert new != old, find_text
            hwp.MoveParaBegin(); hwp.MoveSelParaEnd(); hwp.HAction.Run("Delete")
            hwp.insert_text(new)
        retype_para("2026년", lambda s: re.sub(r"2026년\s+월\s+일", SUBMIT_DATE, s))
        retype_para("팀장 :", lambda s: re.sub(r"팀장 :(\s+)\(서명\)", lambda m: f"팀장 :  {LEADER}" + " " * max(len(m.group(1)) - 8, 3) + "(서명)", s))
        retype_para("팀원 :", lambda s: re.sub(r"팀원 :(\s+)\(서명\)", lambda m: f"팀원 :  {MEMBER}" + " " * max(len(m.group(1)) - 8, 3) + "(서명)", s, count=1))
        # 팀원이 1명이라 비어 있는 둘째 팀원 줄은 지운다
        hwp.MoveDocBegin()
        if hwp.find("팀원 :                 (서명)"):
            hwp.HAction.Run("Cancel"); hwp.MoveParaBegin(); hwp.MoveSelNextParaBegin(); hwp.HAction.Run("Delete")

        # 5) 장별 본문
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

        marker = {"o": " ◦ ", "h": " ◦ ", "-": "   - ", "·": "     ·", "*": "       * "}
        for heading, blocks in chapters:
            hwp.MoveDocBegin(); assert hwp.find(heading), heading
            hwp.MoveParaEnd(); hwp.BreakPara()
            for b in blocks:
                if b[0] == "p":
                    apply(b[1]); hwp.insert_text(marker[b[1]] + b[2]); hwp.BreakPara()
                elif b[0] == "table":
                    rows = b[1]; ncol = max(len(r) for r in rows)
                    apply("cell")
                    ps = hwp.HParameterSet.HTableCreation
                    hwp.HAction.GetDefault("TableCreate", ps.HSet)
                    ps.Rows, ps.Cols, ps.WidthType, ps.HeightType = len(rows), ncol, 2, 0
                    ps.WidthValue = text_width
                    ps.CreateItemArray("ColWidth", ncol)
                    for j, wj in enumerate(col_widths(rows, ncol)):
                        ps.ColWidth.SetItem(j, wj)
                    ps.TableProperties.Width = text_width
                    hwp.HAction.Execute("TableCreate", ps.HSet)
                    tp = hwp.CreateSet("Table"); tp.SetItem("TreatAsChar", 0)   # 글자처럼 취급이면 쪽 경계에서 나뉘지 않고 잘린다
                    tp.SetItem("OutsideMarginTop", hwp.MiliToHwpUnit(1)); tp.SetItem("OutsideMarginBottom", hwp.MiliToHwpUnit(3))
                    hwp.ParentCtrl.Properties = tp
                    hwp.HAction.Run("TableCellBlock"); hwp.HAction.Run("TableCellBlockExtend"); hwp.HAction.Run("TableColEnd")
                    hwp.cell_fill((230, 230, 230))
                    hwp.HAction.Run("TableColBegin")
                    for i, r in enumerate(rows):
                        for j in range(ncol):
                            apply("cellh" if i == 0 else "cell")
                            hwp.insert_text(r[j] if j < len(r) else "")
                            if not (i == len(rows) - 1 and j == ncol - 1):
                                hwp.HAction.Run("TableRightCell")
                    hwp.MoveParentList(); hwp.MoveParaEnd(); hwp.BreakPara()
                elif b[0] == "fig":
                    n, cap = b[1], b[2]
                    path = HERE / "figures" / FIGS[n]
                    w, h = Image.open(path).size
                    apply("center")
                    hwp.insert_picture(str(path), sizeoption=1, width=FIG_WIDTH_MM, height=round(FIG_WIDTH_MM * h / w))
                    hwp.BreakPara()
                    apply("cap"); hwp.insert_text(f"[그림 {n}] {cap}"); hwp.BreakPara()
        hwp.save_as(str(OUT), "HWPX")
        hwp.save_as(str(OUT.with_suffix(".pdf")), "PDF")
        print("저장:", OUT.name, OUT.with_suffix(".pdf").name)
    finally:
        hwp.quit()
    scrub_lastsaveby(OUT)
    survey_on_new_page(OUT)
    from pyhwpx import Hwp as _Hwp
    h2 = _Hwp(visible=False)
    try:
        h2.set_message_box_mode(0x10000); h2.open(str(OUT)); h2.save_as(str(OUT.with_suffix('.pdf')), 'PDF')
    finally:
        h2.quit()


def scrub_lastsaveby(path: Path):
    """hwpx 메타데이터의 마지막 저장자(PC 사용자 이름)를 비운다. 항목 순서·압축 방식은 그대로 둔다(mimetype 먼저, 무압축)"""
    import zipfile
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "Contents/content.hpf":
                data = re.sub(rb'(<opf:meta name="lastsaveby" content="text">)[^<]*(</opf:meta>)', rb"\1\2", data)
            dst.writestr(info, data)
    tmp.replace(path)



def survey_on_new_page(path: Path):
    """만족도 조사 제목 앞의 빈 문단을 지우고 그 문단에 쪽 나눔을 건다(hwpx XML 직접 수정)."""
    import zipfile
    with zipfile.ZipFile(path) as z:
        infos = z.infolist(); data = {i.filename: z.read(i.filename) for i in infos}
    x = data["Contents/section0.xml"].decode("utf-8")
    k = x.index("경진대회 만족도 조사 완료")
    head = x.rfind("<hp:p ", 0, k)
    removed = 0
    while True:
        end = head
        if not x[:end].endswith("</hp:p>"):
            break
        start = x.rfind("<hp:p ", 0, end)
        para = x[start:end]
        texts = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", para, flags=re.S))
        if texts.strip() or re.search(r"<hp:(tbl|pic|rect|container|ctrl|secPr)", para):
            break
        x = x[:start] + x[end:]
        head = start
        removed += 1
    tag_end = x.index(">", head)
    tag = x[head:tag_end]
    tag = re.sub(r'pageBreak="\d"', 'pageBreak="1"', tag)
    x = x[:head] + tag + x[tag_end:]
    data["Contents/section0.xml"] = x.encode("utf-8")
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as dst:
        for info in infos:
            dst.writestr(info, data[info.filename])
    tmp.replace(path)
    print("만족도 조사 앞 빈 문단 삭제", removed)


if __name__ == "__main__":
    main()
