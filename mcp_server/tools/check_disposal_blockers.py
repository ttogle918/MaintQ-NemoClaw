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

from data.rules import engine

from ..db import read_only

# 자산 참조 규약(`asset_id | equipment_id` 해석·처분 인자 검증)은 `04 §8`·`§14` 공용이라
# `_asset_ref` 에 한 벌만 둔다. 두 도구가 같은 입력에 다른 `reason` 을 내는 드리프트를
# 구조로 막는 것이 목적이며, `spikes/bundle_integrity.py` 의 대조 회귀는 그대로 남는다.
from ._asset_ref import err as _err, parse_disposal_args, resolve_asset_id

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

# 엔진 반환 중 **MCP 계약(`04 §8` output)에 싣는 키만** 화이트리스트로 고정한다.
# 여기 없는 엔진 키(`facts_used`·`laws_used` 등 D82 산출물)는 MCP 출력에 나가지 않는다.
# 새 키를 계약에 넣으려면 `04 §8` 을 먼저 고치고 이 목록에 추가한다 — 그 순서를 강제하는 것이 목적.
_ENGINE_CONTRACT_KEYS = (
    "asset_id",
    "evaluated_at",
    "verdict",
    *_BUCKETS,
    "not_considered",
    "disclaimer",  # 아래에서 completeness 접미사를 붙여 덮어쓴다
)


def _evidence_completeness(
    laws: dict[str, engine.LawRef], rules: dict[str, engine.Rule], result: dict
) -> str:
    """인용 조문이 전부 수집됐는가. MQ-701 실수집 이후 실 DB 정상값은 `COMPLETE` 다
    (7건 중 6건 `FETCHED`, 처분 룰이 인용하는 조문은 전부 포함).

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

        resolved_id, failure = resolve_asset_id(con, asset_id, equipment_id)
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

    # ★ 엔진 반환을 `**result` 로 펼치지 않는다 (계약 고정, `04 §8`).
    # 엔진에 키가 늘면 스프레드는 그것을 **조용히 MCP 계약으로 승격**시킨다.
    # 실제로 `facts_used`·`laws_used`(D82) 가 그렇게 샜다 — 계약에 없는 키가 LLM 페이로드에
    # 자산당 13키만큼 얹혔다. 두 값의 소비처(근거 번들·REST)는 엔진을 직접 호출하므로
    # MCP 출력에 실을 이유가 없다. 계약을 넓히는 대신 좁게 유지한다.
    missing = [k for k in _ENGINE_CONTRACT_KEYS if k not in result]
    if missing:
        # 엔진이 계약 키를 빠뜨렸다. 부분 응답을 정상으로 포장하지 않는다 (D9).
        return _err("engine_error", f"룰 엔진 반환에 계약 키가 없습니다: {', '.join(missing)}")

    return {
        "status": "ok",
        **{k: result[k] for k in _ENGINE_CONTRACT_KEYS},
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
        # 입력 검증·폴백 금지 규약(`disposal_mode` enum, ISO 날짜)은 `_asset_ref` 한 곳에 있다.
        # `build_evidence_bundle` 과 **같은 reason·같은 문구**를 내야 하기 때문이다.
        args, failure = parse_disposal_args(asset_id, equipment_id, disposal_mode, disposal_date)
        if args is None:
            # 배타적 반환 — `args` 가 없으면 `failure` 가 반드시 있다 (`resolve_asset_id` 와 같은 규약).
            return failure or _err("invalid_input", "처분 인자를 해석하지 못했습니다")
        return _run(args.asset_id, args.equipment_id, args.disposal_mode, args.disposal_date)

    except engine.RuleIntegrityError as e:
        # 근거 없는 룰이 카탈로그에 있다 (D61). 판정을 내면 근거 없는 판정이 된다.
        return _err("rule_integrity", f"룰 카탈로그 무결성 위반: {e}")
    except (sqlite3.Error, OSError) as e:
        return _err("db_error", str(e))
    except Exception as e:  # noqa: BLE001 — 엔진 예외를 status 로 바꿔 반환한다 (D9)
        return _err("engine_error", f"{type(e).__name__}: {e}")
