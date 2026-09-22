# data/

원본 데이터는 git에 올리지 않습니다 (X-ray 2.3GB 포함, KAMP 배포 데이터).

KAMP 포털(https://www.kamp-ai.kr/noticeList, 제6회 과제공개 공지)에서 데이터셋 ZIP을 받아 아래처럼 풉니다.
스크립트는 `claude/data/2_용접기/` 경로를 씁니다.

```
data/
├─ 1_사출성형기/        moldset_labeled_cn7.csv 등 4개
├─ 2_용접기/            Welding Data Set_01.xlsx, scaled_data.csv
├─ 3_소성가공_예지보전/  press_data_normal.csv, outlier_data.csv
├─ 4_X-ray_검사장비/
└─ 5_자원최적화/         okm_augumented_2021.csv
```

무결성 확인: `Welding Data Set_01.xlsx` SHA-256 = `d514d6aaa121630c04d7d51c97a56025e78e2c86868813f7722ba5db922c1f33`
