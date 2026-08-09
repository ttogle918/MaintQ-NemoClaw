# -*- coding: utf-8 -*-
"""check_disposal_blockers — 자산 처분의 법정 조건 판정 (S9 진입점).

판정 자체는 **하지 않는다.** 룰 엔진(`data.rules.engine`)이 낸 결과를 그대로 싣는다.
이 파일이 하는 일은 넷뿐이다 — ⓐ 입력 검증 ⓑ 자산 해석 ⓒ 룰 카탈로그 적재 확인
ⓓ 조문 수집 상태 표시.

지켜야 할 것 (전부 "조용히 통과"를 막는 장치다)

  - **`assets` 행을 판정기에 직접 넘기지 않는다. 반드시 `engine.build_facts()` 를 경유한다 (D62).**
    `evaluate_rule` 의 누락 검사는 `f not in facts` 로 **키 존재만** 보므로 `dict(row)` 를 그대로
    넘기면 NULL 이 "값 있음"으로 읽혀 `INSUFFICIENT_FACTS` 여야 할 자산이 조용히 `CLEAR` 가 된다.
    "모른다"가 "조건 미해당"으로 바뀌는 단 하나의 지점이다 (`05_DB_SCHEMA §11` 경고 블록).
  - **`disposal_mode` 는 `engine.DISPOSAL_MODES` 를 단일 출처로 검증한다.** enum 밖 값(`"SELL"`)을
    그대로 흘리면 `VAT-INVOICE` 트리거(`eq "SALE"`)를 빗나가 **오타 하나가 `CONDITIONAL` 을
    `CLEAR` 로** 만든다. 그래서 폴백하지 않고 `invalid_input` 으로 되돌린다.
  - **verdict 5종(D79)을 재계산하지 않는다.** 우선순위(`blockers > holds > insufficient >
    preconds > CLEAR`)는 `engine.check_disposal_blockers()` 안에만 있어야 한다. 여기서 다시
    조립하면 구 4종(`insufficient` 를 `HOLD` 에 흡수)으로 되돌아가는 회귀가 조용히 들어오고,
    D71 의 HTTP 매핑(409/200)이 함께 깨진다.
  - **룰 카탈로그 미적재는 `not_found` 가 아니라 `error` 다 (D50).** 0행을 "조건 없음"으로 주면
    모든 자산이 `CLEAR` 로 통과한다 — `lookup_error_code` 의 `catalog_not_loaded` 와 같은 논리.
  - **예외를 던지지 않는다 (D9·D46).** 엔진은 `RuleIntegrityError` 말고도 `KeyError`(미등록 법령
    참조)·`TypeError`(`trigger` 파손)·`ValueError`(시점 밖 조문)를 던지므로 한 종류만 잡으면
    안 된다. 광범위하게 포착해 `status:"error"` 로 닫는다.
  - 읽기 전용 커넥션만 쓴다 (D10). 이 도구에는 쓰기 경로가 없다.

**판정의 근거는 정본 파일, 적재 확인·조문 상태는 DB 사본**이다(D60). `engine.check_disposal_blockers()`
가 `data/rules/{laws,rules}/*.json` 을 읽으므로 verdict·버킷은 전부 파일 한 곳에서 온다 — 파일과 DB 를
섞어 조립하지 않는다. DB 사본은 ⓒ 적재 게이트와 `fetch_status` 조회에만 쓴다
(시드 검증 ⑮ 와 같은 구조이며, 두 사본이 어긋나면 `data/seed.py` ⑬⑭ 가 먼저 잡는다).

`mcp_server` 는 `backend` 를 import 하지 않는다(D15). `data.rules.engine` 은 데이터 계층이라 허용된다(D73).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from data.rules import engine

from ..db import read_only

DESCRIPTION = (
    "설비 자산의 처분(매각·폐기·이전) 가능 여부를 법정 조건으로 판정한다. "
    "처분·매각·폐기 이야기가 나오면 가장 먼저 호출할 것. 판정은 조문 근거와 함께 나오며, "
    "BLOCKED 면 처분을 진행하지 말고 해소 경로를 안내할 것. "
    "HOLD·INSUFFICIENT_FACTS 를 '문제 없음'으로 해석하지 말 것 — 각각 경계 구간과 사실 부족이다. "
    "이 도구는 판정만 한다. 처분 확정은 사람의 서명으로만 이뤄진다."
)

# engine.check_disposal_blockers() 가 돌려주는 판정 버킷 4종 (D79 의 우선순위 근거)
_BUCKETS = ("blockers", "preconditions", "holds", "insufficient")

_LAW_PENDING_NOTE = " 인용 조문의 원문은 아직 수집되지 않았으며 인용은 조문 번호·제목 기준이다."

# "문자열이 아닌 값이 들어왔다" 를 None(미지정)과 구분하기 위한 표식.
# 둘을 뭉치면 `asset_id=123` 이 조용히 "asset_id 미지정" 이 된다.
_NOT_TEXT = object()


def _err(reason: str, message: str) -> dict:
    return {"status": "error", "reason": reason, "message": message}


def _as_text(value: object) -> object:
    """문자열로 확정되는 값만 통과시킨다. 숫자·dict·list 는 추정하지 않는다."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return _NOT_TEXT


def _resolve_asset_id(
    con: sqlite3.Connection, asset_id: str | None, equipment_id: str | None
) -> tuple[str | None, dict | None]:
    """(asset_id, 실패 응답) 중 하나를 채워 돌려준다.

    `equipment_id` 만 주어지면 `equipment.asset_id` 로 해석한다 (D68). 그 값이 NULL 이면
    `no_host_asset` — `INV-L1-01`(분전반)이 정확히 이 케이스다. **배전 위치는 거래 단위가
    아니므로** 처분 판정 대상이 될 수 없고, 이를 `unknown_*` 이나 `CLEAR` 로 뭉개면
    "판정할 수 없는 대상"이 "판정 결과 문제 없음"으로 읽힌다.

    둘 다 주어졌는데 서로 다른 자산을 가리키면 `invalid_input` 이다 — 한쪽을 조용히 이기게
    하면 사용자가 물은 것과 다른 자산의 판정을 돌려주게 된다.
    """
    resolved: str | None = None
    if equipment_id is not None:
        row = con.execute(
            "SELECT asset_id FROM equipment WHERE equipment_id = ?", (equipment_id,)
        ).fetchone()
        if row is None:
            return None, {
                "status": "not_found",
                "reason": "unknown_equipment",
                "equipment_id": equipment_id,
                "message": f"등록되지 않은 설비입니다: {equipment_id}",
            }
        if row["asset_id"] is None:
            return None, {
                "status": "not_found",
                "reason": "no_host_asset",
                "equipment_id": equipment_id,
                "message": (
                    f"{equipment_id} 에 연결된 호스트 자산이 없습니다 — 처분 판정의 대상은 "
                    "거래 단위인 자산(assets)이며 이 설비에는 그 자산이 지정돼 있지 않습니다. "
                    "판정 결과가 '문제 없음'인 것이 아닙니다."
                ),
            }
        resolved = row["asset_id"]

    if asset_id is not None and resolved is not None and asset_id != resolved:
        return None, _err(
            "invalid_input",
            f"asset_id({asset_id}) 와 equipment_id 가 가리키는 자산({resolved}) 이 다릅니다. "
            "하나만 지정하세요.",
        )
    return (asset_id or resolved), None


def _evidence_completeness(
    laws: dict[str, engine.LawRef], rules: dict[str, engine.Rule], result: dict
) -> str:
    """인용 조문이 전부 수집됐는가. 현재는 7건 전부 `PENDING` 이라 `LAW_TEXT_PENDING` 이 정상값이다.

    판정에 실제로 쓰인 **룰 카탈로그 전체의 법령 참조**를 본다. 출력에 드러난 인용만 세면
    전 룰이 `CLEAR` 인 자산에서 인용이 0건이 되어 `"COMPLETE"` 가 나오는데, 그건 조문을
    수집했다는 뜻이 아니라 아무것도 발화하지 않았다는 뜻이다 — 같은 DB 상태에 두 답이 나온다.

    `is_fetched` 는 `fetch_status == 'FETCHED'` **이면서 원문이 있을 때만** 참이다.
    상태만 보고 통과시키면 본문 없는 행이 완전한 근거로 계산된다.
    """
    referenced: set[str] = set()
    for rule in rules.values():
        referenced.update(rule.law_refs or [])
    for bucket in _BUCKETS:
        for item in result.get(bucket, []):
            referenced.update(item.get("law_refs") or [])

    for law_ref_id in referenced:
        law = laws.get(law_ref_id)
        if law is None or not law.is_fetched:
            return "LAW_TEXT_PENDING"
    return "COMPLETE"


def _run(
    asset_id: str | None,
    equipment_id: str | None,
    disposal_mode: str,
    disposal_date: str | None,
) -> dict:
    with read_only() as con:
        # ── 룰 카탈로그 적재 확인 (D50). 자산 해석보다 먼저 본다 —
        #    카탈로그가 비었으면 어떤 자산을 물어도 판정 자체가 성립하지 않는다.
        laws = engine.load_laws_from_db(con)
        if not laws:
            return _err(
                "rule_catalog_not_loaded",
                "법령 참조(law_refs)가 적재돼 있지 않습니다 — 처분 조건이 없다는 뜻이 아니라 "
                "근거 계층이 비어 있다는 뜻입니다. data/seed.py 를 먼저 실행하세요.",
            )
        rules = engine.load_rules_from_db(con, laws)
        if not rules:
            return _err(
                "rule_catalog_not_loaded",
                "해석 룰(rules)이 적재돼 있지 않습니다 — 조건 미해당이 아니라 카탈로그 미적재입니다.",
            )

        resolved_id, failure = _resolve_asset_id(con, asset_id, equipment_id)
        if failure is not None:
            return failure

        row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (resolved_id,)).fetchone()
        if row is None:
            return {
                "status": "not_found",
                "reason": "unknown_asset",
                "asset_id": resolved_id,
                "message": f"등록되지 않은 자산입니다: {resolved_id}",
            }

        # ★ NULL 컬럼의 키를 빼는 유일한 지점 (D62). dict(row) 를 직접 넘기지 않는다.
        facts = engine.build_facts(row, disposal_mode=disposal_mode, disposal_date=disposal_date)

    # 판정은 엔진이 한다. verdict 우선순위(D79)를 여기서 다시 계산하지 않는다.
    result = engine.check_disposal_blockers(facts)

    verdict = result.get("verdict")
    if verdict not in engine.VERDICTS:
        # 엔진이 계약 밖 어휘를 냈다. 모르는 판정을 통과로 포장하지 않는다.
        return _err("engine_error", f"룰 엔진이 계약 밖 verdict 를 반환했습니다: {verdict!r}")

    completeness = _evidence_completeness(laws, rules, result)
    disclaimer = result["disclaimer"]
    if completeness == "LAW_TEXT_PENDING":
        disclaimer += _LAW_PENDING_NOTE

    return {
        "status": "ok",
        **result,
        # 판정 조건을 결과에 함께 싣는다 — 같은 자산도 mode·날짜에 따라 판정이 갈리므로
        # (`AST-L3-LIFT`: SALE→CONDITIONAL / SCRAP→CLEAR) 이 두 값 없이는 결과를 재현·구분할 수 없다.
        "disposal_mode": disposal_mode,
        "disposal_date": disposal_date,
        "evidence_completeness": completeness,
        "disclaimer": disclaimer,
    }


def check_disposal_blockers(
    asset_id: str | None = None,
    equipment_id: str | None = None,
    disposal_mode: str = "SALE",
    disposal_date: str | None = None,
) -> dict:
    """자산 처분의 법정 조건을 판정한다. 실패는 예외가 아니라 `status` 로 돌려준다 (D9·D46)."""
    try:
        parsed_asset = _as_text(asset_id)
        parsed_equipment = _as_text(equipment_id)
        for name, value in (("asset_id", parsed_asset), ("equipment_id", parsed_equipment)):
            if value is _NOT_TEXT:
                return _err("invalid_input", f"{name} 는 문자열 식별자입니다 (예: 'AST-L3-CONV')")
        if parsed_asset is None and parsed_equipment is None:
            return _err("invalid_input", "asset_id 또는 equipment_id 중 하나는 필요합니다")

        # 미지정(None)은 시그니처 기본값과 같은 뜻으로 본다. 값이 **있는데** enum 밖이면
        # 폴백하지 않는다 — 'SELL'/'sale' 을 SALE 로 고쳐 주면 오타가 판정을 조용히 바꾼다.
        parsed_mode = _as_text(disposal_mode)
        mode = "SALE" if parsed_mode is None else parsed_mode
        if mode is _NOT_TEXT or mode not in engine.DISPOSAL_MODES:
            return _err(
                "invalid_input",
                f"disposal_mode 는 {' | '.join(engine.DISPOSAL_MODES)} 중 하나여야 합니다: "
                f"{disposal_mode!r} (대소문자·유사어를 임의로 해석하지 않습니다)",
            )

        parsed_date = _as_text(disposal_date)
        if parsed_date is _NOT_TEXT:
            return _err(
                "invalid_input", "disposal_date 는 ISO 날짜 문자열입니다 (예: '2026-08-09')"
            )
        if parsed_date is not None:
            try:
                date.fromisoformat(parsed_date)
            except ValueError:
                # 판독 불가한 날짜를 오늘로 메우면 "처분일을 모른다"가 "오늘 처분한다"가 된다 (D62).
                return _err(
                    "invalid_input",
                    f"disposal_date 를 ISO 날짜로 읽을 수 없습니다: {disposal_date!r} "
                    "(예: '2026-08-09'). 모르는 날짜를 오늘로 대체하지 않습니다.",
                )

        return _run(parsed_asset, parsed_equipment, mode, parsed_date)

    except engine.RuleIntegrityError as e:
        # 근거 없는 룰이 카탈로그에 있다 (D61). 판정을 내면 근거 없는 판정이 된다.
        return _err("rule_integrity", f"룰 카탈로그 무결성 위반: {e}")
    except (sqlite3.Error, OSError) as e:
        return _err("db_error", str(e))
    except Exception as e:  # noqa: BLE001 — 엔진 예외를 status 로 바꿔 반환한다 (D9)
        return _err("engine_error", f"{type(e).__name__}: {e}")
