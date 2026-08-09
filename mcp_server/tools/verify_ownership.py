# -*- coding: utf-8 -*-
"""verify_ownership — 중고 설비 실사 체크리스트 판정 (S18, `12 §6` 9개 카테고리).

**이 도구는 "안전합니다"라고 말하지 않는다.** 무엇을 확인했고 **무엇이 남았는지**를 말한다
(`11 §6` S18). 그래서 설계가 다음 세 가지로 고정돼 있다:

1. 원천이 없는 항목은 **무조건 `UNVERIFIED` + `limit`**(왜 확인할 수 없는지). 비어 있는 이력을
   "문제 없음"으로 읽지 않는다 — 그게 D62 가 막으려는 "모른다 → 통과" 다.
2. `UNVERIFIED` 가 하나라도 있으면 최대 `PARTIAL` 이고, **`PARTIAL` 은 어떤 조건으로도
   `VERIFIED` 로 승격되지 않는다** (`11 §6`). 코드에 승격 경로 자체가 없다 (`_verdict` 참조).
3. **외부 기관을 런타임에 호출하지 않는다** (`.env.example` §외부 데이터 원천) — 요청마다
   기관을 호출하면 "서명 시점 스냅샷 재현" 전제가 깨진다. 등기·사업자등록·법인등기 항목은
   전부 `UNVERIFIED` + "사전 수집 스냅샷 없음" 이다. 이 모듈은 외부 API 키를 참조하지 않는다.

읽기 전용이다 (`read_only` 만 사용, D10). 실패는 예외가 아니라 `status` 로 돌려준다 (D9·D46).

────────────────────────────────────────────────────────────────────────────────
★ 값을 어디서 읽는가 — **이 규약을 어기면 조용한 오작동이 난다**

  **룰 사실 키**(`engine.ASSET_FACT_COLUMNS` ∪ 엔진 파생 키) → `facts[...]` (키 부재 = 모른다, D62)
  그 **밖**의 컬럼                                        → `row[...]`  (`is None` 으로 직접 판정)

`build_facts` 는 `ASSET_FACT_COLUMNS` 의 컬럼과 **판정 시점 파생 키 4종**(`engine.py:389-396`)만
만든다. 그 밖의 컬럼을 `facts.get()` 으로
읽으면 **DB 에 값이 있어도 항상 None** 이라, 이 도구가 "기록 없음"이라고 서술하게 된다.
실제로 그 결함이 한 번 났다(B-1: `last_overhaul_at` 이 목록 밖인데 `facts.get()` 으로 읽어
오버홀 기록이 있는 `AST-L2-SPDL`·`AST-L4-WRAP` 을 미확인으로 표시). D62 방향으로는 안전하지만
**있는 근거를 없다고 말하는 것**이라 이 도구의 존재 이유와 정면으로 어긋난다.
회귀: `spikes/asset_tools_contract.py ⑲⑳㉑`.

⛔ 해결책으로 `ASSET_FACT_COLUMNS` 에 컬럼을 추가하지 말 것 — 그 목록은 **룰이 읽는 사실**이고,
   룰이 읽지 않는 값을 섞으면 "이 판정이 무엇을 봤는가"가 흐려진다(`engine.py:289-291`).
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

# D73 — `data/` 는 두 프로세스가 공유해도 되는 데이터 계층이다(`backend` ↔ `mcp_server`
# 상호 import 만 금지). `server.py:28` 이 레포 루트를 sys.path 에 넣는다.
# ★ `assets` 행을 그대로 읽지 않고 `build_facts` 를 경유하는 이유: 이 함수가 **NULL 인 컬럼의
#   키를 아예 만들지 않는다.** "값이 없다"와 "값을 모른다"를 한곳에서 같은 규칙으로 판정해야
#   `insured=NULL` 을 "미부보"로 읽는 사고(D78·D62)가 구조적으로 불가능해진다.
from data.rules.engine import ASSET_FACT_COLUMNS, build_facts

from ..db import read_only

# 반복 고장 판정 기준은 `get_error_history` 의 상수를 **재사용**한다 (D2·D29).
# 같은 현상에 도구마다 다른 문턱을 쓰면 같은 자산이 도구에 따라 다르게 판정된다.
from .get_error_history import REPEAT_THRESHOLD, REPEAT_WINDOW_DAYS

DESCRIPTION = (
    "중고 설비를 사거나 팔기 전 실사 체크리스트 9개 카테고리를 판정한다. "
    "권리관계(담보·리스·압류)·정비 이력·법정 요건·시장가 등 '이 설비를 믿고 거래해도 되는가'를 "
    "물을 때 호출할 것. 결과는 확인된 것과 확인되지 않은 것을 나눠서 준다. "
    "verdict 가 PARTIAL 이면 '대체로 안전'이 아니라 '미확인 항목이 남았다'는 뜻이며, "
    "PARTIAL 은 어떤 추가 확인으로도 VERIFIED 로 승격되지 않는다 — 사용자에게 안전하다고 "
    "말하지 말고 남은 항목과 계약상 배분(진술보장·특약)을 안내할 것. "
    "이 도구는 외부 기관(등기·국세청)을 조회하지 않는다 — UNVERIFIED 항목을 "
    "추측으로 메우지 말 것. "
    # 두 파라미터가 스키마상 전부 optional 이라(둘 중 하나 필수는 스키마로 표현되지 않는다)
    # 인자 없이 호출 → invalid_input → 재시도 루프가 스키마로 막히지 않는다. 여기서 막는다.
    "asset_id 또는 equipment_id 중 하나는 반드시 넘길 것 — 둘 다 비우면 조회 없이 거부된다. "
    "설비(인버터) 식별자만 알면 equipment_id 로 호출하면 호스트 자산으로 해석된다."
)

# `build_facts` 가 `ASSET_FACT_COLUMNS` 밖에서 추가로 만드는 **판정 시점 파생 키**
# (`data/rules/engine.py:389-396`): `disposal_mode`·`vat_invoice_issued` 는 항상,
# `disposal_date`·`months_since_acquisition` 은 `disposal_date` 인자를 줬을 때만.
# 이 도구는 `build_facts(row)` 를 인자 없이 부르므로 실제로는 앞의 둘만 존재한다.
# ⚠ 이 목록을 `engine` 의 공개 상수로 승격하지 않는다 — `engine.py` 는 MQ-601b 소유다.
#   대신 출처를 여기 적어 두고, 엔진이 바뀌면 회귀(`spikes/asset_tools_contract.py`)가 잡는다.
ENGINE_DERIVED_FACT_KEYS = frozenset(
    {"disposal_mode", "vat_invoice_issued", "disposal_date", "months_since_acquisition"}
)
FACT_KEYS = frozenset(ASSET_FACT_COLUMNS) | ENGINE_DERIVED_FACT_KEYS

# ---------------------------------------------------------------- 상수

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
PARTIAL = "PARTIAL"

# `12 §6` 실사 체크리스트 9개 카테고리 — 순서·개수 고정. 출력에는 **항상 9개가 전부** 실린다
# (해당 없음이라고 빼면 "확인 안 한 것"이 화면에서 사라진다).
CATEGORIES = (
    "물리적 상태",
    "가동 이력",
    "정비 이력",
    "기술적 진부화",
    "권리관계",
    "법정 요건",
    "재무·회계",
    "시장·가격",
    "이전 비용",
)

# 자주 쓰는 limit 문구 — 같은 이유를 항목마다 다르게 쓰면 "왜 못 확인했나"가 흐려진다
_NO_FIELD_SURVEY = "현장 실사 원천 없음 — 육안·계측 결과를 담는 테이블이 저장소에 없다"
_NO_RUNTIME_HOURS = "가동시간 원천 없음 — 컨트롤러 로그·가동시간 컬럼이 저장소에 없다 (D70)"
_NO_OPS_SOURCE = "생산 운영 원천 없음 — 교대·가공 실적을 담는 테이블이 없다"
# ⛔ 국세청·법인등기·등기소를 런타임에 호출하고 싶어지는 자리. 호출하지 않는다.
_NO_SNAPSHOT = (
    "사전 수집 스냅샷 없음 — 외부 기관을 런타임에 조회하지 않는다 (.env.example §외부 데이터 원천)"
)
_NO_TRANSFER_QUOTE = "이전 견적 원천 없음 — 해체·운송·설치 비용은 현장 조사 후 견적으로만 산출된다"

# 원천이 **아예 존재하지 않는** 항목. 조건 분기 없이 상수로 UNVERIFIED 다.
# 이 표가 비어 있지 않는 한 전 항목 VERIFIED 는 구조적으로 성립하지 않는다.
FIXED_UNVERIFIED: dict[str, tuple[tuple[str, str], ...]] = {
    "물리적 상태": (
        ("정밀도 검사", _NO_FIELD_SURVEY),
        ("진동·소음 측정", _NO_FIELD_SURVEY),
        ("누유 점검", _NO_FIELD_SURVEY),
        ("전장부 상태", _NO_FIELD_SURVEY),
        ("베드·가이드 마모", _NO_FIELD_SURVEY),
    ),
    "가동 이력": (
        ("누적 가동시간", _NO_RUNTIME_HOURS),
        ("스핀들 시간", _NO_RUNTIME_HOURS),
        (
            "알람 이력",
            "error_history 는 인버터 에러코드 이력이며 자산 전체의 알람 이력이 아니다 — "
            "'반복 고장 패턴' 항목에서만 인버터 단위로 사용한다 (D68 ⓑ)",
        ),
        ("교대 패턴", _NO_OPS_SOURCE),
        ("가공 소재", _NO_OPS_SOURCE),
    ),
    "기술적 진부화": (
        ("통신 규격", "통신 옵션·프로토콜을 기록하는 컬럼이 없다"),
        ("제조사 존속", _NO_SNAPSHOT),
    ),
    "권리관계": (
        ("소유자 실재·처분 권한", _NO_SNAPSHOT),
        (
            "동산담보등기 조회",
            "개별 물건 조회 수단이 없다 — 등기정보광장은 집계 통계만 제공",
        ),
        (
            "리스 여부",
            "원천 없음 — 리스는 동산담보등기 대상이 아니고 저장소에 리스 계약 원천이 없다 "
            "(점유가 곧 권리 외관이라 육안으로도 구분되지 않는다)",
        ),
        ("압류·가압류", "원천 없음 — 집행 기록을 담는 테이블이 없다"),
    ),
    "법정 요건": (
        ("안전인증", "인증서 원천 없음 — 인증번호를 기록하는 컬럼이 없다"),
        ("환경 규제 대상 여부", "환경 인허가 원천 없음"),
    ),
    "재무·회계": (
        (
            "내용연수 결정",
            "내용연수 결정 근거 원천 없음 — 잔가곡선의 기준내용연수는 목업 파라미터이지 "
            "이 자산의 내용연수 결정이 아니다 (D65·D74)",
        ),
    ),
    "시장·가격": (
        ("감정평가서", "감정평가서 원천 없음"),
        ("매도 사유", "매도인 진술 원천 없음"),
    ),
    "이전 비용": (
        ("해체·상차", _NO_TRANSFER_QUOTE),
        ("운송", _NO_TRANSFER_QUOTE),
        ("반입 경로", _NO_TRANSFER_QUOTE),
        ("설치·정렬", _NO_TRANSFER_QUOTE),
        ("시운전", _NO_TRANSFER_QUOTE),
    ),
}

# UNVERIFIED 항목 → 잔여 위험 문장. 여기 없는 항목은 마지막에 건수로만 합산된다.
RISK_BY_ITEM: dict[str, str] = {
    "리스 여부": "리스 물건일 가능성 배제 불가",
    "동산담보등기 조회": "제3자 담보권 존재 가능성 배제 불가",
    "소유자 실재·처분 권한": "매도인 실재·처분 권한 미확인",
    "압류·가압류": "집행 절차 진행 여부 미확인",
    "정기점검 기록": "정비 이력 미확인 — 상태 리스크를 가격에 반영할 수 없다",
    "핵심부품 교체": "핵심부품 교체 이력 미확인",
    "오버홀": "오버홀 실시 여부 미확인",
    "반복 고장 패턴": "반복 고장 여부 미확인",
    "정밀도 검사": "현장 실사 미실시 — 물리적 상태 리스크 잔존",
    "안전검사": "안전검사 유효성 미확인 — 인수 후 즉시 검사 의무가 발생할 수 있다",
    "동일 기종 거래가": "시장 비교가 부재 — 매매가 적정성을 검증할 수 없다",
    "해체·상차": "이전 비용 미산정 — 총 취득원가가 확정되지 않는다",
    "감가상각 명세": "장부가 미확인 — 처분손익을 계산할 수 없다",
}

MITIGATION_BY_ITEM: dict[str, str] = {
    "리스 여부": "매도인 진술보장 + 손해배상 특약으로 계약상 배분 권고",
    "동산담보등기 조회": "매도인 진술보장 + 손해배상 특약으로 계약상 배분 권고",
    "소유자 실재·처분 권한": "계약 체결 전 사업자등록증·법인등기부 사본을 서면으로 징구",
    "정기점검 기록": "인수 전 정비 이력 서면 요구 — 미제공 자체를 리스크 항목으로 계상",
    "정밀도 검사": "인수 전 현장 실사·시운전 조건부 계약 권고",
    "안전검사": "인수 시점 안전검사 유효기간을 서면으로 확인",
    "동일 기종 거래가": "복수 딜러 호가 수집 또는 감정평가로 가격 근거 확보",
    "해체·상차": "해체·운송·설치 견적을 총 취득원가에 포함해 재평가",
}

NOT_CONSIDERED = (
    "외부 기관 실시간 조회(동산담보등기·사업자등록·법인등기) — 런타임 호출 금지, 사전 수집 스냅샷 없음",
    "현장 실사(정밀도·진동·누유·마모) — 저장소에 원천 없음",
    "가동시간·스핀들 시간 기반 지표 — 원천 없음 (D70)",
    "감정평가·실거래 비교가 — 잔가곡선은 목업 추정치이며 실거래가 아니다 (D65·D74)",
    "리스·압류처럼 점유 외관과 어긋나는 권리 (11 §6 S18)",
)

DISCLAIMER = (
    "이 결과는 확인된 것과 확인되지 않은 것을 구분해 보여줄 뿐, 이 자산이 안전하다고 말하지 않는다. "
    "UNVERIFIED 는 '문제 없음'이 아니라 '확인 수단이 없음'이다. "
    "PARTIAL 은 이 도구 안에서 어떤 조건으로도 VERIFIED 로 승격되지 않는다 (11 §6). "
    "시장·잔가 관련 수치는 법정 기준내용연수 기반 목업 추정치이며 실거래가가 아니다 (D65·D74)."
)

# 잔가 격자 (MQ-603 산출물과 동일). 격자 밖 연차는 행이 없으므로 조회하지 않는다.
_AGE_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (0, 2, "0-2"),
    (3, 5, "3-5"),
    (6, 10, "6-10"),
    (11, 15, "11-15"),
    (16, 20, "16-20"),
    (21, 30, "21-30"),
)


# ---------------------------------------------------------------- 항목 조립 헬퍼


def _item(name: str, state: str, evidence: str | None = None, limit: str | None = None) -> dict:
    """항목 1건. UNVERIFIED 면 `limit` 이 반드시 있어야 한다 — 이유 없는 미확인은 만들지 않는다."""
    if state == UNVERIFIED and not limit:
        limit = "확인 원천 없음"
    return {
        "item": name,
        "state": state,
        "evidence": evidence if state == VERIFIED else None,
        "limit": limit if state == UNVERIFIED else None,
    }


def _unverified(name: str, limit: str) -> dict:
    return _item(name, UNVERIFIED, limit=limit)


def _verified(name: str, evidence: str) -> dict:
    return _item(name, VERIFIED, evidence=evidence)


def _fixed(category: str) -> list[dict]:
    return [_unverified(name, limit) for name, limit in FIXED_UNVERIFIED.get(category, ())]


def _assert_fact_column(col: str) -> None:
    """모듈 docstring 의 "값을 어디서 읽는가" 규약을 **주석이 아니라 코드로** 강제한다.

    B-1 이 난 이유는 규약이 사람의 기억에만 있었기 때문이다. 목록 밖 컬럼을 `facts` 에서
    읽으면 조용히 None 이 나와 "기록 없음"으로 서술되므로, 여기서 시끄럽게 실패시킨다
    (도구 진입점이 전부 포착해 `status:"error"` 로 닫는다 — 사용자에게 거짓 서술이 가는 것보다 낫다).

    허용 집합은 `ASSET_FACT_COLUMNS` **∪ 엔진 파생 키**다 — `build_facts` 가 목록 밖에서도
    `disposal_mode` 등 4종을 만들기 때문이다. 여기를 `ASSET_FACT_COLUMNS` 로만 좁히면
    나중에 `vat_invoice_issued` 를 **정당하게 읽으려는 코드까지 가드가 거짓 차단**한다.
    """
    if col not in FACT_KEYS:
        raise KeyError(
            f"{col!r} 은 룰 사실 키가 아니다 (ASSET_FACT_COLUMNS ∪ 엔진 파생 키 밖) — "
            "facts 에 절대 들어오지 않으므로 row[...] 에서 읽어야 한다 "
            "(모듈 docstring 규약 · B-1)"
        )


def _knows(facts: dict, col: str) -> bool:
    """그 사실을 **아는가**. 키 부재 = 모른다 (D62)."""
    _assert_fact_column(col)
    return col in facts


def _fact(facts: dict, col: str) -> Any:
    _assert_fact_column(col)
    return facts.get(col)


def _age_bucket(acquired: date | None, today: date) -> str | None:
    if acquired is None:
        return None
    age = today.year - acquired.year - ((today.month, today.day) < (acquired.month, acquired.day))
    for low, high, label in _AGE_BUCKETS:
        if low <= age <= high:
            return label
    return None  # 격자 밖(음수·31년 이상) — 보간하지 않는다 (D65 와 같은 태도)


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 카테고리별 판정


def _maintenance_items(con: sqlite3.Connection, row: sqlite3.Row, eq_ids: list[str]) -> list[dict]:
    """정비 이력 — **서명된 수리 레코드만** 센다 (`12 §11`).

    0행이면 `UNVERIFIED` 다. **빈 이력을 "문제 없음"으로 읽지 않는다** — 정비를 안 한 것인지
    기록을 안 한 것인지 구분할 수 없고, 매도인이 이력을 주지 않는 것 자체가 리스크다 (`12 §6`).

    `facts` 를 받지 않는다 — 이 카테고리가 읽는 자산 컬럼(`last_overhaul_at`)은
    `ASSET_FACT_COLUMNS` 밖이라 `facts` 에 존재할 수 없다 (모듈 docstring 규약 · B-1).
    """
    items: list[dict] = []
    if not eq_ids:
        no_eq = "이 자산에 연결된 인버터가 없어 수리 레코드를 조회할 수 없다"
        items.append(_unverified("정기점검 기록", no_eq))
        items.append(_unverified("핵심부품 교체", no_eq))
    else:
        # f-string 으로 조립되는 건 **자리표시자(?)뿐**이고 값은 전부 파라미터 바인딩이다
        marks = ",".join("?" * len(eq_ids))
        rows = con.execute(
            f"SELECT work_type, part_class, cost, signed_at FROM repair_records "
            f"WHERE equipment_id IN ({marks}) AND signed_at IS NOT NULL",
            eq_ids,
        ).fetchall()
        unsigned = con.execute(
            f"SELECT count(*) FROM repair_records WHERE equipment_id IN ({marks}) "
            f"AND signed_at IS NULL",
            eq_ids,
        ).fetchone()[0]
        planned = [r for r in rows if r["work_type"] == "PLANNED"]
        critical = [r for r in rows if r["part_class"] == "CRITICAL"]
        skipped = f" · 미서명 {unsigned}건은 제외" if unsigned else ""

        if planned:
            items.append(
                _verified("정기점검 기록", f"서명된 PLANNED 수리 {len(planned)}건{skipped}")
            )
        else:
            items.append(
                _unverified(
                    "정기점검 기록",
                    f"서명된 정기점검 레코드 0건{skipped} — 점검을 안 한 것인지 기록이 없는 것인지 "
                    "구분할 수 없다 (빈 이력은 '문제 없음'이 아니다)",
                )
            )
        if critical:
            total = sum(r["cost"] or 0 for r in critical)
            items.append(
                _verified(
                    "핵심부품 교체",
                    f"서명된 CRITICAL 부품 수리 {len(critical)}건 · 합계 {total:,}원{skipped}",
                )
            )
        else:
            items.append(
                _unverified(
                    "핵심부품 교체",
                    f"서명된 핵심부품 교체 레코드 0건{skipped} — 교체 이력 없음으로 읽을 수 없다",
                )
            )

    # 오버홀 — `assets.last_overhaul_at`. NULL 은 "미실시"가 아니라 "모른다"다 (D62)
    # ★ `row` 에서 읽는다 — 이 컬럼은 `ASSET_FACT_COLUMNS` **밖**이라 `facts` 에는 절대 없다
    #   (모듈 docstring 의 "값을 어디서 읽는가" 규약 · B-1). `facts.get()` 으로 읽으면 DB 에
    #   값이 있어도 항상 None 이라 오버홀 기록이 있는 자산까지 "기록 없음"이 된다.
    overhaul = row["last_overhaul_at"]
    if overhaul:
        items.append(_verified("오버홀", f"최근 오버홀 {overhaul} (assets.last_overhaul_at)"))
    else:
        items.append(
            _unverified(
                "오버홀",
                "assets.last_overhaul_at 이 비어 있다 — 오버홀 미실시인지 기록 누락인지 구분할 수 없다",
            )
        )

    # 반복 고장 패턴 — **인버터 단위 판정**(D68 ⓑ), asset 하위 equipment 전체를 집계만 한다
    if not eq_ids:
        items.append(
            _unverified(
                "반복 고장 패턴", "이 자산에 연결된 인버터가 없어 에러 이력을 집계할 수 없다"
            )
        )
        return items

    marks = ",".join("?" * len(eq_ids))
    counts = con.execute(
        f"SELECT equipment_id, count(*) AS c FROM error_history "
        f"WHERE equipment_id IN ({marks}) AND occurred_at >= datetime('now', ?) "
        f"GROUP BY equipment_id",
        [*eq_ids, f"-{REPEAT_WINDOW_DAYS} day"],
    ).fetchall()
    hit = [(r["equipment_id"], r["c"]) for r in counts if r["c"] >= REPEAT_THRESHOLD]
    total_events = sum(r["c"] for r in counts)
    if total_events == 0:
        items.append(
            _unverified(
                "반복 고장 패턴",
                f"최근 {REPEAT_WINDOW_DAYS}일 에러 이력 0건 — 무고장인지 미기록인지 구분할 수 없다",
            )
        )
    elif hit:
        detail = ", ".join(f"{eid} {c}회" for eid, c in hit)
        items.append(
            _verified(
                "반복 고장 패턴",
                f"반복 고장 감지 — {REPEAT_WINDOW_DAYS}일 {REPEAT_THRESHOLD}회 기준 초과 ({detail})",
            )
        )
    else:
        items.append(
            _verified(
                "반복 고장 패턴",
                f"반복 고장 미감지 — {REPEAT_WINDOW_DAYS}일 내 {total_events}건 "
                f"(인버터별 최대 {max(r['c'] for r in counts)}회 < {REPEAT_THRESHOLD}회)",
            )
        )
    return items


def _obsolescence_items(con: sqlite3.Connection, row: sqlite3.Row, models: list[str]) -> list[dict]:
    """기술적 진부화 — 제어기 세대 / 부품 단종(D20)."""
    items: list[dict] = []
    generation = row["controller_generation"]
    if generation is not None and str(generation).strip():
        items.append(_verified("제어기 세대", f"{generation} (assets.controller_generation)"))
    else:
        items.append(_unverified("제어기 세대", "assets.controller_generation 이 비어 있다"))

    eol_flag = bool(row["parts_eol_flag"])
    if not models:
        items.append(
            _unverified(
                "부품 단종",
                "이 자산에 연결된 인버터가 없어 호환 부품을 특정할 수 없다 "
                f"(assets.parts_eol_flag={int(eol_flag)} 만으로는 근거가 부족하다)",
            )
        )
        return items + _fixed("기술적 진부화")

    rows = con.execute("SELECT part_no, compatible_models, discontinued FROM parts").fetchall()
    related, discontinued, unknown = [], [], []
    for r in rows:
        try:
            compat = json.loads(r["compatible_models"])
        except (TypeError, ValueError):
            compat = []
        if not any(m in compat for m in models):
            continue
        related.append(r["part_no"])
        if r["discontinued"] is None:
            unknown.append(r["part_no"])
        elif r["discontinued"]:
            discontinued.append(r["part_no"])

    if not related:
        items.append(
            _unverified("부품 단종", f"기종 {'/'.join(models)} 에 호환되는 부품 레코드가 0건")
        )
    elif unknown:
        items.append(
            _unverified(
                "부품 단종",
                f"호환 부품 {len(related)}종 중 {len(unknown)}종의 단종 여부가 미기재 "
                f"({', '.join(unknown[:3])}…)",
            )
        )
    else:
        note = (
            f"단종 {len(discontinued)}종 ({', '.join(discontinued)})"
            if discontinued
            else "단종 0종"
        )
        items.append(
            _verified(
                "부품 단종",
                f"호환 부품 {len(related)}종 중 {note} · assets.parts_eol_flag={int(eol_flag)}",
            )
        )
    return items + _fixed("기술적 진부화")


def _rights_items(facts: dict) -> list[dict]:
    """권리관계 — 사내 기록으로 확인 가능한 담보·부보만 판정하고 나머지는 고정 UNVERIFIED."""
    items: list[dict] = []

    # 담보 — `build_facts` 경유라 NULL 컬럼은 **키 자체가 없다** (D62)
    if not _knows(facts, "has_lien"):
        items.append(
            _unverified(
                "담보 설정 (사내 기록)", "assets.has_lien 이 NULL — 담보 설정 여부를 모른다"
            )
        )
    elif _fact(facts, "has_lien"):
        creditor = _fact(facts, "lien_creditor") or "채권자 미기재"
        consent = _fact(facts, "lien_consent_ref")
        detail = f"동의서 {consent}" if consent else "처분 동의서 미확보"
        items.append(_verified("담보 설정 (사내 기록)", f"담보 설정 있음 — {creditor} · {detail}"))
    else:
        items.append(
            _verified("담보 설정 (사내 기록)", "사내 기록상 담보 설정 없음 (assets.has_lien=0)")
        )

    # 부보 여부 — D78 의 3상태를 **그대로** 반영한다.
    #   키 없음(NULL)=모름 → UNVERIFIED / False=확인된 미부보 → VERIFIED(단, 위험은 남는다) / True=부보
    # ⛔ NULL 을 "미부보"로 읽지 않는다 — 그 순간 "모른다"와 "없다"가 섞인다 (D62 정면 위반).
    if not _knows(facts, "insured"):
        items.append(
            _unverified(
                "부보 여부",
                "assets.insured 가 NULL — 부보 여부를 모른다 (미부보로 읽지 않는다, D78·D62)",
            )
        )
    elif _fact(facts, "insured"):
        policy = _fact(facts, "policy_id")
        detail = f"증권 {policy}" if policy else "증권번호 미기재"
        items.append(_verified("부보 여부", f"부보 확인 (assets.insured=1) · {detail}"))
    else:
        items.append(
            _verified(
                "부보 여부",
                "확인된 미부보 (assets.insured=0) — 사실은 확인됐으나 무보험 위험은 그대로 남는다",
            )
        )
    return items + _fixed("권리관계")


def _statutory_items(facts: dict, today: date) -> list[dict]:
    """법정 요건 — 안전검사."""
    items: list[dict] = []
    if not _knows(facts, "safety_inspection_target"):
        items.append(
            _unverified(
                "안전검사", "assets.safety_inspection_target 이 NULL — 검사 대상 여부를 모른다"
            )
        )
    elif not _fact(facts, "safety_inspection_target"):
        items.append(
            _verified("안전검사", "안전검사 비대상으로 기록됨 (safety_inspection_target=0)")
        )
    else:
        last = _fact(facts, "last_inspection_date")
        until = _fact(facts, "inspection_valid_until")
        if not last or not until:
            items.append(
                _unverified(
                    "안전검사",
                    "안전검사 대상인데 최근 검사일·유효기간 중 일부가 비어 있다 "
                    f"(last={last or 'NULL'} / until={until or 'NULL'})",
                )
            )
        else:
            until_date = _as_date(until)
            expired = until_date is not None and until_date < today
            state = "만료됨" if expired else "유효"
            items.append(_verified("안전검사", f"최근 검사 {last} · 유효기간 {until} ({state})"))
    return items + _fixed("법정 요건")


def _finance_items(row: sqlite3.Row, facts: dict) -> list[dict]:
    """재무·회계 — 감가상각 명세 / 매도인 세액공제."""
    items: list[dict] = []
    cost, book = row["acquisition_cost"], row["book_value"]
    if cost is None or book is None:
        missing = " · ".join(
            n for n, v in (("acquisition_cost", cost), ("book_value", book)) if v is None
        )
        items.append(_unverified("감가상각 명세", f"{missing} 이 NULL — 장부가를 산출할 수 없다"))
    else:
        items.append(
            _verified(
                "감가상각 명세", f"취득원가 {cost:,}원 · 장부가 {book:,}원 (사내 고정자산 기록)"
            )
        )

    if not _knows(facts, "tax_credit_applied"):
        items.append(
            _unverified(
                "매도인 세액공제",
                "assets.tax_credit_applied 가 NULL — 공제 적용 여부를 모른다 "
                "(미적용으로 읽으면 추징 대상이 무표시로 통과한다)",
            )
        )
    else:
        applied = (
            "적용됨 — 처분 시 추징 여부 확인 필요"
            if _fact(facts, "tax_credit_applied")
            else "미적용"
        )
        items.append(
            _verified("매도인 세액공제", f"세액공제 {applied} (assets.tax_credit_applied)")
        )
    return items + _fixed("재무·회계")


def _market_items(
    con: sqlite3.Connection, row: sqlite3.Row, facts: dict, today: date
) -> list[dict]:
    """시장·가격 — `residual_curve` 는 **참고치**로만 싣고 상태는 UNVERIFIED 로 남긴다.

    잔가곡선은 법정 기준내용연수 기반 **목업 공식** 산출물이다(D74) — 실거래 비교가 아니므로
    "동일 기종 거래가를 확인했다"고 말할 수 없다 (D65: 없는 정확도를 있는 척하지 않는다).
    참고치는 `limit` 문장에 그대로 실어 근거는 잃지 않는다.
    """
    category = row["category"]
    bucket = _age_bucket(_as_date(_fact(facts, "acquired_at")), today)
    total = con.execute("SELECT count(*) FROM residual_curve").fetchone()[0]

    if total == 0:
        return [
            _unverified(
                "동일 기종 거래가", "residual_curve 0행 — 시장가 참고 원천이 적재되지 않았다"
            )
        ] + _fixed("시장·가격")
    if bucket is None:
        limit = (
            "취득일을 알 수 없거나 연차가 잔가 격자(0~30년) 밖이라 참고 잔가율을 특정할 수 없다 "
            "— 인접 구간으로 보간하지 않는다 (D65)"
        )
        return [_unverified("동일 기종 거래가", limit)] + _fixed("시장·가격")

    hit = con.execute(
        "SELECT residual_ratio, source FROM residual_curve WHERE category = ? AND age_bucket = ?",
        (category, bucket),
    ).fetchone()
    if hit is None:
        limit = f"residual_curve 에 (카테고리 {category!r}, 연차 {bucket}) 행이 없다"
    else:
        limit = (
            f"실거래 비교가 아님 — 참고 잔가율 {hit['residual_ratio']} "
            f"(카테고리 {category!r} · 연차 {bucket}) 는 {hit['source']}"
        )
    return [_unverified("동일 기종 거래가", limit)] + _fixed("시장·가격")


# ---------------------------------------------------------------- verdict · 잔여위험


def _verdict(items: list[dict]) -> str:
    """미확인이 하나라도 있으면 **최대 PARTIAL**.

    ⛔ 승격 경로가 없다. 이 함수는 항목 상태만 보고, 호출자는 반환값을 한 번만 대입한다
    (`11 §6` — PARTIAL 은 어떤 조건으로도 VERIFIED 가 되지 않는다).
    아래 마지막 줄은 승격 분기가 아니라 **전 항목 확인의 기저 케이스**이며,
    `FIXED_UNVERIFIED`(리스·동산담보등기·현장 실사 등)가 항상 목록에 들어가므로
    이 도구에서는 도달할 수 없다 — DoD 의 "시드 9자산 전부 PARTIAL 이하"가 그 확인이다.
    """
    if any(i["state"] == UNVERIFIED for i in items):
        return PARTIAL if any(i["state"] == VERIFIED for i in items) else UNVERIFIED
    return VERIFIED


def _dedup(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        seen.setdefault(v, None)
    return list(seen)


def _residual_risk(items: list[dict], confirmed_risks: list[str]) -> str | None:
    """잔여 위험은 **UNVERIFIED 항목에서 조립**한다. 전부 확인되면 None.

    `confirmed_risks` 는 "확인됐지만 위험은 남는" 사실(예: `insured=0` 확인된 미부보)이다 —
    확인됐다는 이유로 위험이 사라지지 않으므로 같은 문장에 함께 싣는다.
    """
    unverified = [i["item"] for i in items if i["state"] == UNVERIFIED]
    phrases = _dedup([RISK_BY_ITEM[i] for i in unverified if i in RISK_BY_ITEM])
    if unverified and not phrases:
        phrases = [f"확인되지 않은 항목 {len(unverified)}건 잔존"]
    elif unverified:
        phrases.append(f"그 밖 미확인 항목 포함 총 {len(unverified)}건 잔존")
    phrases.extend(confirmed_risks)
    return " · ".join(phrases) if phrases else None


def _mitigation(items: list[dict], confirmed_mitigations: list[str]) -> str | None:
    unverified = [i["item"] for i in items if i["state"] == UNVERIFIED]
    steps = _dedup([MITIGATION_BY_ITEM[i] for i in unverified if i in MITIGATION_BY_ITEM])
    steps.extend(confirmed_mitigations)
    return " · ".join(steps) if steps else None


# ---------------------------------------------------------------- 진입점


def verify_ownership(asset_id: str | None = None, equipment_id: str | None = None) -> dict:
    """실사 체크리스트 9개 카테고리를 판정한다. 예외를 던지지 않는다 (D9·D46)."""
    try:
        return _verify(asset_id, equipment_id)
    except FileNotFoundError as e:
        return {"status": "error", "reason": "db_missing", "message": str(e)}
    except sqlite3.Error as e:
        return {"status": "error", "reason": "db_error", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — engine·파싱 예외까지 status 로 닫는다 (D9)
        return {
            "status": "error",
            "reason": "internal_error",
            "message": f"{type(e).__name__}: {e}",
        }


def _resolve_asset(con: sqlite3.Connection, asset_id: str | None, equipment_id: str | None) -> Any:
    """`asset_id` 우선, 없으면 `equipment.asset_id` 로 해석한다 (공통 규약).

    호스트 자산이 없는 인버터(`INV-L1-01` 분전반)는 `no_host_asset` 이다 — 배전 위치이지
    거래 가능한 기계가 아니라서, 실사 대상이 "없다"는 사실 자체를 돌려줘야 한다.
    """
    if asset_id:
        row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "reason": "unknown_asset", "asset_id": asset_id}
        return row

    eq = con.execute(
        "SELECT equipment_id, asset_id FROM equipment WHERE equipment_id = ?", (equipment_id,)
    ).fetchone()
    if eq is None:
        return {"status": "not_found", "reason": "unknown_equipment", "equipment_id": equipment_id}
    if eq["asset_id"] is None:
        return {
            "status": "not_found",
            "reason": "no_host_asset",
            "equipment_id": equipment_id,
            "message": f"{equipment_id} 에 연결된 호스트 자산이 없습니다 — 실사 대상이 아닙니다 (D68)",
        }
    row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (eq["asset_id"],)).fetchone()
    if row is None:
        return {"status": "not_found", "reason": "unknown_asset", "asset_id": eq["asset_id"]}
    return row


def _verify(asset_id: str | None, equipment_id: str | None) -> dict:
    if not isinstance(asset_id, (str, type(None))) or not isinstance(
        equipment_id, (str, type(None))
    ):
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "asset_id·equipment_id 는 문자열입니다",
        }
    asset_id = asset_id.strip() if asset_id else None
    equipment_id = equipment_id.strip() if equipment_id else None
    if not asset_id and not equipment_id:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "asset_id 또는 equipment_id 중 하나는 필요합니다",
        }

    with read_only() as con:
        resolved = _resolve_asset(con, asset_id, equipment_id)
        if isinstance(resolved, dict):
            return resolved
        row = resolved
        today = datetime.now(timezone.utc).date()

        # ★ NULL 컬럼의 키를 만들지 않는 유일한 경로 (D62). `assets` 행을 직접 읽어 판정하면
        #   NULL 이 "값 있음"으로 새어 들어간다 — 특히 `insured`·`tax_credit_applied`.
        facts = build_facts(row)

        eq_rows = con.execute(
            "SELECT equipment_id, model FROM equipment WHERE asset_id = ? ORDER BY equipment_id",
            (row["asset_id"],),
        ).fetchall()
        eq_ids = [r["equipment_id"] for r in eq_rows]
        models = _dedup([r["model"] for r in eq_rows if r["model"]])

        by_category: dict[str, list[dict]] = {
            "물리적 상태": _fixed("물리적 상태"),
            "가동 이력": _fixed("가동 이력"),
            "정비 이력": _maintenance_items(con, row, eq_ids),
            "기술적 진부화": _obsolescence_items(con, row, models),
            "권리관계": _rights_items(facts),
            "법정 요건": _statutory_items(facts, today),
            "재무·회계": _finance_items(row, facts),
            "시장·가격": _market_items(con, row, facts, today),
            "이전 비용": _fixed("이전 비용"),
        }

    categories = [{"category": c, "items": by_category[c]} for c in CATEGORIES]
    items = [i for c in categories for i in c["items"]]

    # 확인됐지만 위험이 남는 사실 — 확인 상태가 위험을 지우지 않는다
    confirmed_risks: list[str] = []
    confirmed_mitigations: list[str] = []
    if _knows(facts, "insured") and _fact(facts, "insured") is False:
        confirmed_risks.append("확인된 미부보 — 인도 전 손해 발생 시 보상 없음 (assets.insured=0)")
        confirmed_mitigations.append("인도 전 부보 또는 위험부담 특약 필요")

    return {
        "status": "ok",
        "asset_id": row["asset_id"],
        "verdict": _verdict(items),  # 대입은 여기 한 번뿐 — 이후 어떤 분기도 이 값을 바꾸지 않는다
        "categories": categories,
        "verified": [f"{i['item']} — {i['evidence']}" for i in items if i["state"] == VERIFIED],
        "unverified": [f"{i['item']} — {i['limit']}" for i in items if i["state"] == UNVERIFIED],
        "residual_risk": _residual_risk(items, confirmed_risks),
        "mitigation": _mitigation(items, confirmed_mitigations),
        "not_considered": list(NOT_CONSIDERED),
        "disclaimer": DISCLAIMER,
    }
