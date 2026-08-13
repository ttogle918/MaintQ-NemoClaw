"""data-analysis 노트북 공용 유틸 — 경로 상수 · 컬럼 프로파일 · 결정 로그 저장.

⛔ 원본을 복사하지 않는다. `data/raw/` 는 읽기 전용이고 git 에도 올라가지 않는다
   (CLAUDE.md 절대규칙 5 · D60 "원본은 파일이 정본"). 노트북은 여기 상수로 원본을
   **제자리에서 읽고**, 산출물만 `data-analysis/` 안으로 내보낸다.

노트북 상단에서:
    import sys; sys.path.insert(0, "..")
    from common import RAW, EXTRACTED, PROCESSED, REPORTS, profile, save_decisions
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------- 경로
# 이 파일은 <repo>/data-analysis/common.py 이므로 parent.parent 가 저장소 루트다.
REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_ROOT = REPO_ROOT / "data-analysis"

# 읽기 전용 원본 (저장소 본체 — 복사하지 않는다)
RAW = REPO_ROOT / "data" / "raw"
EXTERNAL = RAW / "external"
EXTRACTED = REPO_ROOT / "data" / "extracted"
IROS = REPO_ROOT / "data" / "iros"
LAWS = REPO_ROOT / "data" / "rules" / "laws"
RULES = REPO_ROOT / "data" / "rules" / "rules"

# 쓰기 대상 (이 디렉터리 안에서만)
PROCESSED = ANALYSIS_ROOT / "data" / "processed"
REPORTS = ANALYSIS_ROOT / "reports"

for _d in (PROCESSED, REPORTS):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- 프로파일
def profile(df: pd.DataFrame, sample: int = 3) -> pd.DataFrame:
    """"이 데이터가 실제로 어떻게 생겼나"를 한 표로 —
    컬럼 / dtype / null 비율 / 고유값 수 / 예시값.

    ⚠ null 비율만 보면 안 된다. 중진공 CSV 의 `제조년월` 은 결측률 0% 인데
      결측 자리에 `확인불가` **문자열**이 들어 있다(data_list.md §6-1). 그래서
      `예시값` 컬럼을 같이 낸다 — 눈으로 봐야 잡히는 함정이다.
    """
    rows = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        vals = s.dropna().unique()[:sample]
        rows.append(
            {
                "컬럼": col,
                "dtype": str(s.dtype),
                "null수": int(s.isna().sum()),
                "null%": round(s.isna().mean() * 100, 2) if n else 0.0,
                "고유값": int(s.nunique(dropna=True)),
                "예시값": " | ".join(str(v)[:28] for v in vals),
            }
        )
    return pd.DataFrame(rows)


def top_values(df: pd.DataFrame, col: str, n: int = 10) -> pd.DataFrame:
    """빈도 상위 n개를 건수·비율과 함께. 문자열 함정(공백·표기 변종) 확인용."""
    vc = df[col].value_counts(dropna=False).head(n)
    return pd.DataFrame(
        {
            col: [repr(i) for i in vc.index],  # repr — '환경  설비' 의 공백 2칸이 보이도록
            "건수": vc.to_numpy(),
            "비율%": (vc / len(df) * 100).round(2).to_numpy(),
        }
    )


# ---------------------------------------------------------------- 산출물 저장
def save_decisions(dataset: str, column_decisions: list[dict[str, Any]], **extra: Any) -> Path:
    """결정 로그를 reports/{dataset}_decisions.json 으로 저장하고 요약을 출력한다."""
    used = [d for d in column_decisions if d.get("used")]
    payload = {
        "dataset": dataset,
        "column_total": len(column_decisions),
        "column_used": len(used),
        "column_decisions": column_decisions,
        **extra,
    }
    path = REPORTS / f"{dataset}_decisions.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {path.relative_to(REPO_ROOT)}  ({len(used)}/{len(column_decisions)} 컬럼 사용)")
    return path


def save_processed(dataset: str, df: pd.DataFrame) -> Path:
    """정제본을 data/processed/{dataset}.parquet 으로 저장."""
    path = PROCESSED / f"{dataset}.parquet"
    df.to_parquet(path, index=False)
    print(f"✅ {path.relative_to(REPO_ROOT)}  ({len(df):,}행 × {len(df.columns)}열)")
    return path
