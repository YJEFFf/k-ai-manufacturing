"""모델 산출물 계약 — PLAN.md §7. predict.py는 이 파일만 읽어 추론한다(재학습·재선택 없음).

JSON 하나에 protocol_version·모델·분할·전처리·창·입력 해시와 학습 상태(state)를 담는다.
state는 2단계(점수 변환·보정)에서 채운다. 1단계 뼈대에서는 state가 비어 있을 수 있고, 그 경우
predict.py는 점수를 내지 않고 입력 검증·기록구간·행 상태만 출력한다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .data import PROTOCOL_VERSION, to_jsonable

ARTIFACT_VERSION = 1


@dataclass
class Artifact:
    model_id: str
    split: str
    preprocess: str
    w: int | None
    input_sha256: dict
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    protocol_version: str = PROTOCOL_VERSION
    artifact_version: int = ARTIFACT_VERSION
    state: dict = field(default_factory=dict)  # scaler, 참조 점수, u/beta, 보정 최댓값, 문턱 등 (2단계)

    @property
    def trained(self) -> bool:
        return bool(self.state)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(to_jsonable(asdict(self)), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Artifact":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d.get("artifact_version") != ARTIFACT_VERSION:
            raise ValueError(f"artifact_version {d.get('artifact_version')} 은 지원하지 않는다")
        return cls(**d)
