"""Build a 50-item evidence ledger; presence, decoding and review are distinct."""
from pathlib import Path
import collections
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

NOTES = {
1:'저울 숫자 OCR. 이물 위치 정답이나 공정 품질 정답을 보충하지 않음. ZIP 내부 전 항목 CRC 확인.',
2:'③ 엔진 진동의 다른 설비 검증 후보. 실제 고장·운전 조건과 분할은 원본 접근 후 확인 필요.',
3:'CNC 가공 이상 탐지 방법 참고. 프레스 펌프와 센서·공정 동일성은 없음.',
4:'① 대회 원본 별도 확보·4개 CSV 전수 검사. 동일 센서 입력의 라벨 충돌 및 제품 간 이전 실패 확인.',
5:'② 대회 원본 재확보·엑셀 전 시트 확인. 건별 품질 정답 없음, 센서 고유 벡터 1,574개/11,939행.',
6:'사출품·열화상 영상 방법 참고 후보. 공정 센서와 동일 제품 연결 가능 여부 미확인.',
7:'프레스 공정 참고 후보. ③ 펌프 고장 정답의 추가 사례인지 미확인.',
8:'835,200행 전수 파싱. 품질 판정 자료이며 펌프 고장 정답 아님. 가이드 양품 F1과 고장 성능 구별.',
9:'③ 교반 설비 진동 참고 후보. 설비·고장 단위 독립 검증 가능성 미확인.',
10:'살균기 공정 참고. 가이드 확보. 다섯 과제의 동일 대상 정답을 추가한다는 근거 없음.',
11:'③ 건조 설비 진동 참고 후보. 실제 라벨·수집 구간 원본 확인 필요.',
12:'④ 영상·TXT 전수 확인, 후반 모델 가중치 생략. 고유 라벨 영상 500장·1,147객체·24일·3검사기. 정상 확정 0장, TXT 버전 충돌 3개.',
16:'현장 문자 인식용. EGG 5,161개 항목 CRC 통과, 체크포인트 1개 해제 오류. 이물 정답 보충 아님.',
18:'③ 회전기계 고장 유형 후보. 원본·가이드 접근 대기; 일반화 개선 효과 미검증.',
19:'생산 운영·병목 최적화 방법 참고. ⑤ 전력 절감 실증 데이터라고 볼 근거 없음.',
20:'도금 전해탈지 공정 이상 진단 방법 참고. 용접/펌프 고장 정답 대체 불가.',
21:'도금욕 공정 이상 진단 방법 참고. 다른 공정의 이상 탐지 성능은 별도 표시 필요.',
23:'임시 파일 761196은 정상 ZIP(217항목 CRC 통과). 정상 WAV 170개는 고유 30개 반복. 파일 무작위 분할 누출.',
25:'④ 도금 표면 영상 1,452개를 가이드에서 확인. X-ray 아님. 센서 분기는 전체 자료 학습 후 테스트 평가 코드. 원 ZIP 0바이트.',
26:'⑤ 수요 예측 방법 참고 후보. 전력 및 생산계획과 연결 가능한지 원본 미검증.',
27:'⑤ 대회 원본 6,168×18 확인. 공장인원 파생열의 정답 누출, 시간 오염, 날짜 반복을 통제한 미래 예측 실험.',
28:'① 다른 성형 조건 최적화 참고 후보. 원본 조건과 품질 정답의 연결 미검증.',
29:'임시 EGG에서 XML 7,648개 전수 검사. 사람 검출 영상이며 X-ray 아님. 검증 95.7%가 학습 이웃 프레임.',
30:'⑤ 생산계획 최적화 방법 참고 후보. 전력 부하를 실제로 옮길 수 있는 제약과 동일성 미검증.',
36:'⑤ 생산·출고 일정 참고 후보. 공장 전력 실증의 독립 데이터라고 판단하지 않음.',
37:'⑤ 수요 불확실성 방법 참고 후보. 원본 분석 대기.',
40:'34,617×20 전수 검사. 117제품의 공급망 자료이며 사출 품질 정답을 추가하지 않음.',
41:'원본 24,479행·249일 확인. 시각 중복 576개·습도 음수, 가이드 물리량 혼용. 27과 공통 원천 정황 있어 독립 전력 검증으로 간주하지 않음.',
42:'화장품 가이드의 Power는 공정 전력 측정이나 단위 미제시. 표본 간격·기간 연결 확인 없이 연속시계열로 가정 금지.',
43:'③ 열처리 설비 이상 참고 후보. 동명 ZIP 0바이트, 임시 파일 대응 미확인.',
44:'정밀가공 자원·생산 최적화 참고. 대회 전력 현장의 인과 효과 근거를 추가하지 않음.',
45:'이전 77쪽 가이드 검토 기록 존재. 진동·전류 이상 선별이며 점용접 제품 검사 정답 아님. 동명 ZIP 0바이트.',
46:'83쪽 가이드 전체 검토. 전류를 에너지로 오해하면 안 됨. 음수 R², 범위 밖 수량 최적화, 절감 37%는 시뮬레이션.',
47:'음향기기 품질 검사 방법 참고. 펌프 음향·용접 불량의 동일 정답 데이터가 아님.',
48:'③ 대회 원본 정상 20,000·이상 600행 전수 검사. 수집 날짜가 클래스와 일치; 이상 사례 수를 600고장으로 해석 금지.',
49:'실제 압출 치수 검사 라벨을 가이드에서 확인. 단 하루·전체 자료 변수 선별 뒤 무작위 평가; 사출 정답 대체 불가.',
50:'정밀가공 품질 방법 참고. 다른 제품의 정답을 대회 사출 또는 용접 건과 연결할 근거 없음.',
51:'가이드상 5개 센서 정상·이상 범위 완전 분리. 미래 예측 출력과 과거 입력의 오차 비교 코드 문제. 원본 대기.',
52:'가이드상 739,888행은 PIPE_NO 303개 반복. 양품 F1 0.9753과 불량 F1 구별. 제품 그룹 분할 필요.',
53:'73,612×23 원본 전수 검사·미래 구간 검증 실행. 주조 자료의 성능이며 사출 대회 성능 아님.',
54:'가이드 목표는 예열 가생산과 정상 생산 구분. 미래 고장 예측으로 과장 금지; 55와 원천 중복 점검 필요.',
55:'가이드의 미검사·결측 품질을 0처리, SMOTE 후 분할 확인. 제품/샷 단위 평가 전 성능 인용 금지.',
56:'ZIP 끝부분 누락. 정상 해제된 앞부분 883,092행 진단만 수행. PassOrFail은 가이드의 분석자 구성 라벨.',
57:'배터리 레이저 용접. N-HiTS 경로의 전체 테스트 오차 분포 사용 확인. 정상 학습 통계 기준모델과 구별.',
58:'배터리 충방전 후공정 검사. 125개 ZIP 항목 CRC, 모든 표 파싱. 가이드 테스트 PCA/scaler 재학습 문제.',
59:'579,297행 전수 검사. 가공본=원본 전방 채움. 이상은 두 연속 구간이며 다른 동시 알람과 완전 동일.',
60:'293만행 센서와 136행 품질 검사. 61과 공통 7열 136행 전부 같아 독립 외부 검증으로 중복 계상 금지.',
61:'60과 같은 열처리 원천. 가이드 약 7개 평가점·전처리 누출, MAE 코드 오표기 확인.',
62:'표 전수 파싱. 최종 34,156행은 125개 Lot의 정답 반복. 가이드 테스트 6,832행 모두 학습과 같은 Lot. 90과 독립 원천으로 세지 않음.',
90:'의류 공정 최적화 가이드 확보. ZIP 불완전으로 원본 실증 미완료; ⑤ 생산 최적화 방법 참고 범위.'}


def main():
    catalog = json.loads(Path('/tmp/kamp_free_catalog.json').read_text())['entries']
    mapping = json.loads((HERE / 'download_source_mapping.json').read_text())
    checks = {r['path']: r for r in json.loads((HERE / 'archive_checks.json').read_text())}
    pdf = {r['source']: r for r in json.loads((HERE / 'pdf_available_inventory.json').read_text())}
    extra = {'12. Dataset_XrayInspection.zip':12, 'Dataset_로봇용접 예지보전 AI 데이터셋.zip':45,
             'Dataset_장비이상 조기탐지 AI 데이터셋.zip':23, 'Dataset_열처리 예지보전 AI 데이터셋.zip':43,
             'Dataset_품질 이상탐지 진단(크로메이트) AI 데이터셋.zip':25}
    grouped = collections.defaultdict(list)
    for r in mapping:
        seqs = r.get('seq_candidates', [])
        seq = int(seqs[0]) if seqs else extra.get(Path(r['path']).name)
        if seq:
            grouped[seq].append(r)
    lines = ['# KAMP 50종 파일별 검증 대장', '', '기준: 2026-09-22. **파일이 있다는 사실, 압축을 정상 해제했다는 사실, 내용으로 성능을 검증했다는 사실을 구별한다.**', '',
             f"49종의 가이드북 파일을 확인했고 이번에 본문을 읽을 수 있었던 것은 {len(pdf)}종이다. 나머지는 iCloud 본문 읽기가 대기했다. 5번 가이드는 이번 다운로드 목록에 없다. 45번은 이전 검토 기록을 별도로 사용했다.", '',
             '아래 데이터 상태는 사용자가 놓은 파일의 검사 결과다. 핵심 대회 5종은 공식 공개 공고의 첨부를 별도로 확보했다. 압축파일은 메모리/스트림에서 해제하여 CRC와 내용을 검사했으며, 모든 파일을 디스크에 풀어 놓았다는 뜻은 아니다.', '',
             '| ID | 자료·공식 출처 | 이번 가이드 접근 | 사용자 데이터 파일 검사 | 의미와 사용 판단 |', '|---:|---|---|---|---|']
    for e in catalog:
        seq=e['seq'];files=grouped[seq];guides=[r for r in files if r['path'].endswith('.pdf')]
        g='본문 추출·핵심 검토' if any(r['path'] in pdf for r in guides) else ('iCloud 읽기 대기' if guides else '파일 없음')
        if seq==45:g+='; 이전 검토 있음'
        statuses=[]
        for r in files:
            if r['path'].endswith('.pdf'):continue
            c=checks.get(r['path'],{});s=c.get('status')
            status={'zip_crc_all_pass':'전체 ZIP CRC 통과','empty_file':'0바이트','archive_error':'ZIP 해제 불가/불완전',
                    'cloud_pending':'iCloud 읽기 대기','egg_format_requires_reader':'별도 EGG 검사'}.get(s)
            if status is None:status='CSV 전수 검사' if seq==53 else ('iCloud 읽기 대기' if r.get('cloud') else '별도 검사')
            statuses.append(status)
        # A later completed read is evidence even if iCloud subsequently evicts it.
        later = HERE / 'energy_vision' / f'raw{seq}.json'
        if later.exists() and seq in [26,27,30,36,37,41,46]:
            detail=json.loads(later.read_text())
            if 'crc_first_bad_member' in detail and detail['crc_first_bad_member'] is None:
                statuses=['전체 ZIP CRC·표 검사(후속 접근 성공)']
        if seq==5:statuses=['기존 대회 엑셀 재확보·동일 해시 확인']
        if seq==23:statuses.append('임시 ZIP 217항목 CRC 통과')
        if seq==29:statuses.append('임시 EGG 15,103항목 CRC 통과·끝부분 부족')
        if seq in [4,12,27,48]:statuses.append('대회 첨부 별도 확보')
        lines.append(f"| {seq} | [{e['title']}]({e['url']}) | {g} | {'; '.join(statuses) or '대응 파일 미확인'} | {NOTES[seq]} |")
    lines += ['', '## 임시 다운로드 파일', '',
              '- `미확인 761196.crdownload`: 확장자와 달리 완전한 ZIP. 건조팬 WAV 및 공정 CSV가 들어 있으며 23번 후보로 대응시켰다. 파일명만으로 폐기하면 안 된다.',
              '- `미확인 32652.crdownload`: 안전관리 EGG. 끝부분이 부족하다. XML 라벨 7,648개는 전부 검사했다.',
              '- 나머지 임시 다운로드 4개는 iCloud 본문 접근이 되지 않아 내용·대응 항목 미확인. 0바이트 동명 ZIP이 있어도 이 임시 파일에 내용이 남아 있을 수 있다.',
              '- Scene-Text EGG의 체크포인트 `log/latest.pth` 한 항목은 현재 판독기에서 해제 오류. 나머지 5,161개 일반 파일은 CRC를 통과했다. 원본 손상 확정과 판독기 한계를 구분한다.', '',
              '## 재현 근거', '',
              '`archive_checks.json`, `*.egg_crc.json`, `misc_table_profiles.json`, `injection/`, `energy_vision/`, `maintenance_audit.json` 및 각 분야 Markdown을 참고한다. 해시·행 수·오류 로그는 원자료를 공개하지 않고도 검사 범위를 확인하기 위한 것이다.']
    (HERE/'자료별_검증대장.md').write_text('\n'.join(lines)+'\n')
    print('entries',len(catalog),'guide_texts',len(pdf))


if __name__=='__main__':
    main()
