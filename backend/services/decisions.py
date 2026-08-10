# -*- coding: utf-8 -*-
"""처분 결정(계층 3) 서비스 — 제출·서명·반려와 문서 렌더 (S10).

────────────────────────────────────────────────────────────────────────────────
★ 이 모듈이 지키는 두 문장
────────────────────────────────────────────────────────────────────────────────
    "BLOCKING 우회 처분 0건"      · "서명 없는 처분 확정 0건"

두 문장은 **4층**으로 지켜진다. 이 모듈은 그중 3층이고, 마지막 층은 스키마다:

  1층  MCP 도구에 UPDATE 권한이 없다 (D10) — `decision_writer` 의 TEMP TRIGGER
  2층  도구 스키마에 `override` 파라미터가 없다 (D81) — LLM 이 우회를 *요청조차* 못 한다
  3층  `sign()` 의 순서 강제 (아래) — 근거 재산출 → override 게이트 → 사유 게이트
  4층  `decisions` 의 CHECK 2종 (`data/seed.py` §14) — **코드 버그로도 뚫리지 않는다**

3층만 있으면 "코드가 맞게 짜여 있다"는 주장이고, 4층이 있으면 "표현이 불가능하다"는 사실이다.
`data/seed.py ⑳` 이 그 CHECK 가 실제로 거부하는지를 INSERT 로 확인한다.

────────────────────────────────────────────────────────────────────────────────
★ `sign()` 의 순서가 계약이다 (D84)
────────────────────────────────────────────────────────────────────────────────
    ① 행 조회 · 없으면 KeyError                        → 404
    ② state != 'pending'                               → 409 (DecisionTransitionError)
    ③ **번들 재산출 · bundle_hash 대조**                → 409 evidence_changed
    ④ 재산출 verdict ∈ BLOCKING 이고 override 아님      → 409 override_required
    ⑤ override 인데 사유 공백                           → 422
    ⑥ UPDATE

**③ 이 ④ 보다 먼저인 이유**: 근거가 바뀐 상태에서 override 를 받으면 *"사람이 본 것과 다른
근거에 서명"* 이 된다. 근거 무결성이 권한 판단보다 앞선다. 순서를 바꾸지 말 것 —
`spikes/approvals_contract.py` 가 *근거 변경 + BLOCKED* 를 동시에 만든 케이스로 이 순서를 잠근다.

**⑤ 를 pydantic 검증으로 올리지 않는 이유**: 본문 검증은 라우팅 직후에 실행되므로 ①~④ 보다
먼저 422 가 나간다. 그러면 *존재하지도 않는 결정*이나 *근거가 바뀐 결정*에 대해 422 가 돌아와
순서 계약이 깨진다. 그래서 검증은 여기(⑤ 자리)에서 하고 라우터가 422 로 매핑한다.

**`verdict_at_signing` 을 재산출 값으로 덮는 이유**: 컬럼 이름이 말하는 것이 *서명 시점*
판정이다. draft 시점 값을 남기면 필드가 거짓말을 한다.

────────────────────────────────────────────────────────────────────────────────
★ 번들 재산출은 `data.rules.engine` 을 **직접** 쓴다 (D73·D15)
────────────────────────────────────────────────────────────────────────────────
backend 는 `mcp_server` 를 import 하지 않는다. 그래서 `build_evidence_bundle` 의 조립 규약
(정준 직렬화·리스트 4종 정렬·`RULE_HASH_FIELDS`)을 이 파일이 **한 벌 더** 갖는다.

  ⚠ 이 중복은 위험하다. 한 글자만 어긋나도 **모든 서명이 `evidence_changed` 로 막힌다.**
    (조용히 통과하는 방향으로 틀리지 않는다는 점이 그나마 안전하다 — 해시는 양방향 검출이다.)
    `spikes/approvals_contract.py` ⑲ 가 **도구가 만든 번들과 이 모듈의 재산출을 직접 대조**해
    드리프트를 잡는다(뮤턴트 확인: `separators` 를 기본값으로 되돌리면 ⑨⑬⑭⑯⑲ 가 FAIL).
    규약을 고칠 일이 생기면 두 파일을 **같은 커밋에서** 고칠 것.
  ⚠ 조문은 반드시 **DB 사본**(`load_laws_from_db`)으로 읽는다 — 도구가 W5(원천 일원화)로
    그렇게 바꿨으므로, 파일 로더를 쓰면 해시가 구조적으로 어긋난다.

저장된 `evidence_bundle` 은 **다시 직렬화하지 않는다.** 도구가 정준 직렬화한 문자열이
그대로 들어 있으므로, 파싱해서 다시 dumps 하면 해시가 흔들릴 여지가 생긴다.
대조는 *재산출 번들의 해시* ↔ *저장된 `bundle_hash` 컬럼* 사이에서만 한다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.db import connect
from backend.services.disposal import RuleCatalogError, _load_catalog, read_only
from backend.services.po import iso_utc
from data.rules import engine  # D73 — 공유 데이터 계층

# ── 판정 어휘 ────────────────────────────────────────────────────────────────
# 서명 시 override 없이는 통과할 수 없는 판정. **`engine.VERDICTS` 파생**이다 —
# 세 값을 손으로 적으면 엔진이 어휘를 늘렸을 때 새 차단 어휘가 조용히 통과한다.
NON_BLOCKING_VERDICTS: tuple[str, ...] = ("CONDITIONAL", "CLEAR")
BLOCKING_VERDICTS: tuple[str, ...] = tuple(
    v for v in engine.VERDICTS if v not in NON_BLOCKING_VERDICTS
)
assert BLOCKING_VERDICTS == ("BLOCKED", "HOLD", "INSUFFICIENT_FACTS"), (
    "차단 어휘가 예상과 다르다 — engine.VERDICTS 가 바뀌었다면 "
    "data/seed.py 의 decisions CHECK 열거도 함께 고칠 것 (자가검증 ㉑)"
)

# 전이 규칙: 목표 상태 → 허용되는 현재 상태 (`services/po.ALLOWED_FROM` 과 같은 형태)
ALLOWED_FROM: dict[str, str] = {"pending": "draft", "signed": "pending", "rejected": "pending"}

# ── 번들 조립 규약 (`04 §14` · `build_evidence_bundle` 과 **동일해야 한다**) ──────
_BUCKETS = ("blockers", "preconditions", "holds", "insufficient")
RULE_HASH_FIELDS = (
    "rule_id",
    "rule_version",
    "label",
    "category",
    "disposal_type",
    "source_type",
    "law_refs",
    "contract_refs",
    "interpretation",
    "required_facts",
    "trigger",
    "boundary",
    "message",
    "resolve_options",
    "confidence",
    "requires_expert_review",
)
_CONTRACT_NOTE = "계약 조항 원문 원천이 저장소에 없다 — 이 근거는 해시로 고정되지 않는다"

# D86 — 증빙 패키지는 **서명 해시로 고정되지 않는다**. 이 사실을 숨기면 계층 3의 존재 이유가
# 무너지므로 응답에 강제로 싣는다.
HASH_FIXED_NOTE = (
    "이 증빙 패키지는 서명 해시로 고정되지 않는다 — bundle_hash 가 고정하는 것은 "
    "근거 번들(laws·rules·evaluated·contracts·facts)뿐이며, 아래 문서는 응답 조립 시점에 "
    "현재 DB 로 렌더한 것이다."
)
# `12 §8` 이 요구한 증빙 4종 중 만들 수 없는 것. **지어내지 않고 없다고 말한다** (D65·D86).
MISSING_SECTIONS = ["감가상각 명세 — 상각 스케줄 원천 없음"]

DISPOSAL_MODE_LABELS = {"SALE": "매각", "SCRAP": "폐기", "TRANSFER": "양도"}

# 보전지표 산식 상수 — `get_maintenance_metrics`(`04 §11`) 와 **같은 값**이어야 한다.
# 두 벌이 존재하는 이유와 드리프트 방어는 `_metrics` docstring 참조.
HOURS_PER_DAY = 24.0
MTBF_BASIS = "calendar_days"
METRICS_WINDOW_MONTHS = 24  # 도구의 DEFAULT_WINDOW_MONTHS 와 같아야 한다
_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")

# `get_maintenance_metrics._DISCLAIMER` 와 **한 글자도 다르면 안 된다** (⑳ 이 대조한다).
# 증빙 패키지는 매수자에게 나가는 문서다 — 이 문장이 빠지면 `null` 이 '양호'로 읽힌다 (D65).
METRICS_DISCLAIMER = (
    "MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격이다(D70). "
    "가동률이 다른 기간·설비 사이의 직접 비교에는 쓸 수 없다. "
    "null 과 insufficient_data 는 '양호'가 아니라 '판단 근거 부족'이다."
)


# ── 예외 (라우터가 HTTP 로 매핑한다. D38 — 403/409/422 를 섞지 않는다) ───────────
class DecisionTransitionError(Exception):
    """현재 상태에서 할 수 없는 전이 → 409."""

    def __init__(self, decision_id: str, current: str, target: str) -> None:
        self.decision_id, self.current, self.target = decision_id, current, target
        super().__init__(
            f"{decision_id} 는 지금 '{current}' 상태라 '{target}' 로 전이할 수 없습니다 "
            f"('{ALLOWED_FROM[target]}' 에서만 가능)"
        )


class EvidenceChanged(Exception):
    """서명 시점 재산출 해시가 저장된 `bundle_hash` 와 다르다 → 409 `evidence_changed`."""

    def __init__(self, decision_id: str, stored: str, recomputed: str, detail: str = "") -> None:
        self.decision_id, self.stored, self.recomputed = decision_id, stored, recomputed
        super().__init__(
            f"{decision_id} 의 근거가 draft 이후 변경됐습니다 — 사람이 본 것과 다른 근거에 "
            f"서명할 수 없습니다. 저장 해시={stored} / 재산출={recomputed}"
            + (f" · {detail}" if detail else "")
        )


class LawTextUnavailable(Exception):
    """인용 조문 원문이 없어 **재산출 자체가 불가능**하다 → 409 `law_text_unavailable`.

    `evidence_changed` 로 뭉개지 않는 이유: 원인이 다르다. 근거가 *바뀐* 게 아니라
    근거를 *해시할 수 없는* 상태이고, 사람이 할 일도 다르다(조문 수집 vs 재검토).
    """

    def __init__(self, decision_id: str, missing: list[str]) -> None:
        self.decision_id, self.missing = decision_id, missing
        super().__init__(
            f"인용 조문의 원문이 수집되지 않아 근거를 재산출할 수 없습니다 "
            f"(미수집 {len(missing)}건: {', '.join(missing)})"
        )


class CitedRuleMissing(Exception):
    """판정이 인용한 룰이 카탈로그에 없다 → 409 `cited_rule_missing`.

    **503 으로 보내지 않는 이유** (`LawTextUnavailable` 을 `evidence_changed` 에서 분리한 것과
    같은 논리): 503 은 "서버 설정/적재가 미완이니 **재시도하라**"는 말이다. 그런데 이 상태는
    카탈로그가 정상 적재된 채로 *판정이 인용한 근거만 사라진* 경우 — 재시도하면 영원히 같은
    답이 오고, 실제로 필요한 것은 **사람의 재검토**(룰 복원 또는 결정 재작성)다.
    적재 미완(`rules`·`law_refs` 0행 등)은 `_load_catalog` 이 `RuleCatalogError` 로 던져
    그대로 503 에 남는다 — 두 경로를 회귀가 **각각** 잠근다 (`approvals_contract` ㉓·㉔).
    """

    # ⛔ `rule_catalog_invalid` 를 쓰지 않는다 — `backend/services/disposal.py:235,286` 이
    #    **같은 문자열을 503 으로** 쓴다(적재 실패). 어휘가 겹치면 프론트가 "재시도하면 풀림"과
    #    "사람이 재검토해야 함"을 `reason` 만으로 가를 수 없다. 상태가 다르면 이름도 달라야 한다.
    reason = "cited_rule_missing"

    def __init__(self, asset_id: str, missing: list[str]) -> None:
        self.asset_id, self.missing = asset_id, missing
        super().__init__(
            f"판정이 인용한 룰을 카탈로그에서 찾지 못했습니다 "
            f"({len(missing)}건: {', '.join(missing)}) — 근거가 바뀌었으므로 "
            "이 결정은 사람이 다시 검토해야 합니다"
        )


class OverrideRequired(Exception):
    """차단 판정에 서명하려면 override 가 필요하다 → 409 `override_required`."""

    def __init__(self, decision_id: str, verdict: str, judgment: dict) -> None:
        self.decision_id, self.verdict, self.judgment = decision_id, verdict, judgment
        super().__init__(
            f"{decision_id} 는 서명 시점 판정이 {verdict} 입니다 — 우회하려면 "
            "override=true 와 사유가 함께 필요합니다 (D63)"
        )


class OverrideReasonRequired(Exception):
    """override=true 인데 사유가 공백 → 422. DB CHECK 가 2차 방어선이다 (D63)."""

    def __init__(self, decision_id: str) -> None:
        self.decision_id = decision_id
        super().__init__(
            f"{decision_id}: override 에는 사유가 필요합니다 — 시스템 판정과 다른 결정은 "
            "누가 왜 그렇게 판단했는지가 남아야 합니다 (D63)"
        )


# ── 정준 직렬화 · 해시 (규약은 `04 §14`) ────────────────────────────────────────
def canonical_json(obj: Any) -> str:
    """정준 직렬화. `mcp_server/tools/build_evidence_bundle.canonical_json` 과 **동일**.

    네 가지가 전부 고정돼야 "같은 사실 → 같은 해시"가 성립한다:
    `sort_keys=True` · `separators=(",",":")` · `ensure_ascii=False` · `engine.text_hash()`.
    (구분자 차이는 `engine.normalize()` 가 흡수하지 **않는다** — 공백을 지우는 게 아니라
     하나로 접기 때문이다.)
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_bundle_hash(bundle: dict) -> str:
    return engine.text_hash(canonical_json(bundle))


def rule_hash(rule: engine.Rule) -> str:
    """룰 **본문** 해시 (W6). `authored_by`·`reviewed_at`·`revision_note` 는 제외 — 메타라
    판정에 무관하고, 넣으면 주석 수정이 '근거 변조'로 보고된다."""
    return engine.text_hash(canonical_json({k: getattr(rule, k) for k in RULE_HASH_FIELDS}))


def now_utc_sql() -> str:
    """SQLite `CURRENT_TIMESTAMP` 와 같은 형태의 **UTC** 문자열 (D39)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── 번들 재산출 (D84) ───────────────────────────────────────────────────────────
def rebuild_bundle(
    con: sqlite3.Connection, asset_id: str, disposal_mode: str, disposal_date: str | None
) -> tuple[dict, str, dict]:
    """`(bundle, bundle_hash, judgment)` — `build_evidence_bundle` 의 조립을 그대로 재현한다.

    ⛔ MCP 도구를 부르지 않는다 (D15). ⛔ 파일 로더(`load_laws`)를 쓰지 않는다 (W5).
    리스트 4종의 정렬 키: `laws`→`law_ref_id` · `rules`·`evaluated`→`(rule_id, rule_version)` ·
    `contracts`→`contract_ref`. `sort_keys` 는 리스트를 정렬해 주지 않으므로 여기서 한다.
    """
    # 적재 미완(0행·무결성 결함) → `RuleCatalogError` → **503** (precheck 와 같은 게이트, D71).
    # 인용 룰 소실은 여기가 아니라 아래 `CitedRuleMissing` → **409** 다 (원인·할 일이 다르다).
    laws, rules = _load_catalog(con)

    row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    if row is None:
        # 자산이 사라졌으면 재산출할 사실이 없다. "근거가 바뀐 것"의 극단이므로 같은 경로로 보낸다.
        raise KeyError(asset_id)

    facts = engine.build_facts(row, disposal_mode=disposal_mode, disposal_date=disposal_date)
    judgment = engine.check_disposal_blockers(facts, laws=laws, rules=rules)
    facts_used = judgment["facts_used"]

    # 4버킷에 실린 룰·조문만이 "이 판정이 인용한 근거"다 (D83)
    cited_keys: set[tuple[str, Any]] = set()
    cited_law_ids: set[str] = set()
    for bucket in _BUCKETS:
        for item in judgment.get(bucket) or []:
            if item.get("rule_id") is not None:
                cited_keys.add((item["rule_id"], item.get("rule_version")))
            cited_law_ids.update(item.get("law_refs") or [])

    rule_entries: list[dict] = []
    contract_refs: set[str] = set()
    # 첫 건에서 바로 던지지 않고 **전부 모아서** 던진다 (`LawTextUnavailable` 과 같은 규약) —
    # 사람이 재검토할 목록을 한 번에 받아야 왕복이 줄어든다.
    missing_rules: list[str] = []
    for rule_id, rule_version in sorted(cited_keys, key=lambda k: (str(k[0]), str(k[1]))):
        rule = rules.get(rule_id)
        if rule is None or rule.rule_version != rule_version:
            missing_rules.append(f"{rule_id} v{rule_version}")
            continue
        rule_entries.append(
            {
                "rule_id": rule.rule_id,
                "rule_version": rule.rule_version,
                "rule_hash": rule_hash(rule),
            }
        )
        contract_refs.update(rule.contract_refs or [])
    if missing_rules:
        # 적재 미완(503)이 아니라 **근거 변경**이다 → 409. 클래스 docstring 참조.
        raise CitedRuleMissing(asset_id, missing_rules)

    # 조문 원문 게이트. **계약 근거(`contract_refs`)는 대상이 아니다** (`04 §14`) —
    # 넣으면 `LIEN-CONSENT` 자산의 번들이 구조적으로 영원히 불가능해진다.
    missing = [
        rid
        for rid in sorted(cited_law_ids)
        if not (laws.get(rid) and laws[rid].is_fetched and laws[rid].text_hash)
    ]
    if missing:
        raise LawTextUnavailable(asset_id, missing)

    evaluated = sorted(
        (
            {
                "rule_id": r.rule_id,
                "rule_version": r.rule_version,
                "verdict": engine.evaluate_rule(r, facts_used, laws).verdict,
                "law_refs": list(r.law_refs or []),
            }
            for r in rules.values()
        ),
        key=lambda e: (str(e["rule_id"]), str(e["rule_version"])),
    )

    bundle = {
        "laws": [
            {
                "law_ref_id": laws[rid].law_ref_id,
                "effective_from": laws[rid].effective_from,
                "text_hash": laws[rid].text_hash,
            }
            for rid in sorted(cited_law_ids)
        ],
        "rules": rule_entries,
        "evaluated": evaluated,
        "contracts": [
            {
                "contract_ref": ref,
                "text_hash": None,
                "hash_fixed": False,
                "note": _CONTRACT_NOTE,
            }
            for ref in sorted(contract_refs)
        ],
        "facts": facts_used,
    }
    return bundle, compute_bundle_hash(bundle), judgment


def _stored_bundle(row: sqlite3.Row) -> dict:
    """저장된 `evidence_bundle` 을 **읽기만** 한다. 다시 직렬화하지 않는다."""
    try:
        parsed = json.loads(row["evidence_bundle"])
    except (TypeError, ValueError) as exc:
        raise RuleCatalogError(
            "evidence_bundle_invalid", f"저장된 근거 번들을 파싱하지 못했습니다: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise RuleCatalogError("evidence_bundle_invalid", "근거 번들이 객체가 아닙니다")
    return parsed


def _replay_args(bundle: dict) -> tuple[str, str | None]:
    """재산출 입력 — 저장된 `facts` 에서 꺼낸다. **별도 컬럼을 두지 않는다** (D84).

    `build_facts` 가 이미 `disposal_mode`·`disposal_date` 를 facts 에 넣으므로 컬럼은
    같은 사실의 두 번째 사본이 되고, 둘이 어긋나면 어느 쪽으로 재산출할지 알 수 없다.
    """
    facts = bundle.get("facts") or {}
    return facts.get("disposal_mode") or "SALE", facts.get("disposal_date")


# ── 조회 ────────────────────────────────────────────────────────────────────────
_DECISION_SELECT = (
    "SELECT d.*, a.name AS asset_name, a.category AS asset_category,"
    " ru.display_name AS requested_by_name, rv.display_name AS reviewed_by_name"
    " FROM decisions d"
    " JOIN assets a ON a.asset_id = d.asset_id"
    " LEFT JOIN users ru ON ru.user_id = d.requested_by"
    " LEFT JOIN users rv ON rv.user_id = d.reviewed_by"
)


def _row_to_decision(r: sqlite3.Row, *, with_bundle: bool = False) -> dict:
    d = dict(r)
    bundle = _stored_bundle(r)
    if with_bundle:
        d["evidence_bundle"] = bundle
    else:
        d.pop("evidence_bundle", None)
    mode, disposal_date = _replay_args(bundle)
    d["disposal_mode"] = mode
    d["disposal_date"] = disposal_date
    d["override"] = bool(d.get("override"))
    # 미등록·NULL 이면 ID 를 그대로 (`services/po._row_to_po` 와 같은 규칙)
    d["requested_by_name"] = d.get("requested_by_name") or d.get("requested_by") or ""
    d["reviewed_by_name"] = d.get("reviewed_by_name") or d.get("reviewed_by") or ""
    d["created_at"] = iso_utc(d.get("created_at"))
    d["signed_at"] = iso_utc(d.get("signed_at"))
    # 서명 시점 판정이 차단 어휘인가 = "우회 없이는 서명 불가"인가
    d["requires_override"] = d.get("verdict_at_signing") in BLOCKING_VERDICTS
    return d


def list_decisions(state: str | None = None, db_path: Path | None = None) -> list[dict]:
    sql = _DECISION_SELECT
    args: list[object] = []
    if state:
        sql += " WHERE d.state = ?"
        args.append(state)
    sql += " ORDER BY d.created_at DESC, d.decision_id DESC"
    with read_only(db_path) as con:
        return [_row_to_decision(r) for r in con.execute(sql, args).fetchall()]


def get_decision(decision_id: str, db_path: Path | None = None) -> dict | None:
    """상세 + 렌더된 문서·증빙 패키지 (D86). **저장하지 않는다.**"""
    with read_only(db_path) as con:
        r = con.execute(
            _DECISION_SELECT + " WHERE d.decision_id = ?", (decision_id,)
        ).fetchone()
        if r is None:
            return None
        d = _row_to_decision(r, with_bundle=True)
        d["documents"] = render_documents(d["evidence_bundle"], con, asset_id=r["asset_id"])
    return d


# ── 문서 렌더 (D86 — 저장하지 않고 응답 조립 시점에 계산) ────────────────────────
def _law_footnotes(bundle: dict, con: sqlite3.Connection) -> list[dict]:
    """인용 조문 각주 — `bundle.laws[].law_ref_id` → `law_refs` 의 `법령명 제N조(제목)`.

    문안을 손으로 적지 않는다. 조문 표기를 코드에 박으면 `11 §2` 가 막으려던
    *"누가 적은 텍스트"* 가 인용 각주 자리에 들어간다.
    """
    out: list[dict] = []
    for entry in bundle.get("laws") or []:
        rid = entry.get("law_ref_id")
        row = con.execute(
            "SELECT law_name, article, clause, title, effective_from, source_url"
            " FROM law_refs WHERE law_ref_id = ?",
            (rid,),
        ).fetchone()
        if row is None:
            # 번들에는 있는데 DB 사본에 없다 — 지어내지 않고 그 사실을 싣는다 (D62)
            out.append({"law_ref_id": rid, "citation": None, "note": "law_refs 사본에 없음"})
            continue
        clause = f" 제{row['clause']}항" if row["clause"] else ""
        out.append(
            {
                "law_ref_id": rid,
                "citation": f"{row['law_name']} 제{row['article']}조{clause}({row['title']})",
                "effective_from": entry.get("effective_from") or row["effective_from"],
                "text_hash": entry.get("text_hash"),
                "source_url": row["source_url"],
            }
        )
    return out


def _rule_texts(bundle: dict, con: sqlite3.Connection) -> dict[tuple[str, int], dict]:
    """`evaluated[]`·`rules[]` 에 실린 `(rule_id, rule_version)` 의 본문을 DB 사본에서 읽는다.

    **버전을 함께 조회하는 이유**: 서명은 *그때 그 버전*에 대해 이뤄진 것이다(D60).
    최신 버전 문안으로 렌더하면 문서가 서명 대상과 다른 말을 하게 된다.
    """
    keys = {
        (e.get("rule_id"), e.get("rule_version"))
        for e in (bundle.get("evaluated") or []) + (bundle.get("rules") or [])
    }
    out: dict[tuple[str, int], dict] = {}
    for rule_id, rule_version in keys:
        row = con.execute(
            "SELECT rule_id, rule_version, label, category, disposal_type, interpretation,"
            " message, resolve_options, confidence, requires_expert_review, law_refs"
            " FROM rules WHERE rule_id = ? AND rule_version = ?",
            (rule_id, rule_version),
        ).fetchone()
        if row is None:
            continue
        item = dict(row)
        item["resolve_options"] = json.loads(item["resolve_options"] or "[]")
        item["law_refs"] = json.loads(item["law_refs"] or "[]")
        item["requires_expert_review"] = bool(item["requires_expert_review"])
        out[(rule_id, rule_version)] = item
    return out


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _months_ago(anchor: datetime, months: int) -> datetime:
    """달력 기준 N개월 전 (도구 `get_maintenance_metrics._months_ago` 와 동일 규칙)."""
    total = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = anchor.day
    while day > 0:
        try:
            return anchor.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    return anchor.replace(year=year, month=month, day=1)


def _metrics(con: sqlite3.Connection, asset_id: str) -> dict:
    """보전지표 — **`get_maintenance_metrics`(`04 §11`) 와 같은 산식**을 backend 에 둔다.

    ⚠ 도구는 `mcp_server` 소유라 import 할 수 없다(D15). 그래서 산식이 두 벌 존재한다.
      복제를 허용하는 대신 **드리프트를 회귀로 잡는다** — `spikes/approvals_contract.py` ⑳
      이 같은 자산에 대해 도구 출력과 이 함수의 값을 직접 대조한다.

    ⚠ **대조 대상은 숫자만이 아니다.** `excluded[]`(무엇을 뺐는가)와 `disclaimer`(null 이
      '양호'가 아니라는 고지)까지 도구와 같아야 한다 — 산식이 같아도 *고지가 갈리면*
      증빙 패키지가 "확인 안 된 항목을 확인된 것처럼" 보이게 된다. 특히 `occurred_at` 파싱
      실패는 **조용히 버리지 않고** 센 뒤 `excluded` 에 싣는다 (D65).
      `excluded` 는 **순서까지** 도구와 같다(⑳ 이 리스트로 비교한다) — 문구를 추가할 일이
      생기면 `get_maintenance_metrics` 의 append 순서를 먼저 보고 같은 자리에 넣을 것.

    산식 근거 (`12 §2` · D70 · `12 §11`):
      MTBF   = 인접 고장 간격(일)의 평균. **가동시간 기준이 아니다** — 저장소에 가동시간
               원천이 없다. 이벤트 2건 미만이면 `null`(0 으로 메우지 않는다).
      MTTR   = 서명된 `repair_records` 의 `downtime_hours` 평균. **서명분만** (`12 §11`).
      가용도 = MTBF[일] / (MTBF[일] + MTTR[시간]/24). 단위를 맞추지 않으면 조용히 낮아진다.
      예방보전 비율 = PLANNED / (PLANNED + UNPLANNED), 서명분만.
      누적 수리비 비율 = cumulative_repair_cost / acquisition_cost (분모 없으면 `null`).
    """
    equipment_ids = [
        r["equipment_id"]
        for r in con.execute(
            "SELECT equipment_id FROM equipment WHERE asset_id = ? ORDER BY equipment_id",
            (asset_id,),
        ).fetchall()
    ]
    excluded: list[str] = []
    moments: list[datetime] = []
    unparsed_events = 0
    repairs: list[sqlite3.Row] = []
    # 기준 시각은 SQLite 의 `datetime('now')`(UTC) — 도구와 같은 기준이어야 창이 어긋나지 않는다
    now = _parse_dt(con.execute("SELECT datetime('now')").fetchone()[0]) or datetime.now(
        timezone.utc
    ).replace(tzinfo=None)
    window_start = _months_ago(now, METRICS_WINDOW_MONTHS)
    if equipment_ids:
        marks = ",".join("?" * len(equipment_ids))
        for r in con.execute(
            f"SELECT occurred_at FROM error_history WHERE equipment_id IN ({marks})"  # noqa: S608
            " ORDER BY occurred_at ASC",
            equipment_ids,
        ).fetchall():
            moment = _parse_dt(r["occurred_at"])
            if moment is None:
                # ⛔ 조용히 버리지 않는다 — 센 다음 `excluded` 에 고지한다 (도구와 같은 태도).
                #    창(window) 밖 이벤트와 달리 이건 *해석 실패*라 창 조건보다 먼저 본다.
                unparsed_events += 1
                continue
            if moment >= window_start:
                moments.append(moment)
        moments.sort()
        repairs = con.execute(
            f"SELECT work_type, downtime_hours, signed_at FROM repair_records"  # noqa: S608
            f" WHERE equipment_id IN ({marks})",
            equipment_ids,
        ).fetchall()

    gaps = [
        (b - a).total_seconds() / 86400.0 for a, b in zip(moments, moments[1:], strict=False)
    ]
    mtbf_days = sum(gaps) / len(gaps) if gaps else None

    signed = [r for r in repairs if r["signed_at"]]
    unsigned_n = len(repairs) - len(signed)
    downtimes = [float(r["downtime_hours"]) for r in signed if r["downtime_hours"] is not None]
    mttr_hours = sum(downtimes) / len(downtimes) if downtimes else None

    # ── 고지 문안: 순서·문구 모두 `get_maintenance_metrics` 와 같다 (⑳ 이 리스트로 대조) ──
    if unsigned_n:
        excluded.append(
            f"서명되지 않은 수리 레코드 {unsigned_n}건은 지표에서 제외했다 "
            "(MTTR·예방보전 비율 분모 모두 — 12 §11)"
        )
    if signed and not downtimes:
        excluded.append(
            "서명된 수리 레코드에 downtime_hours 가 하나도 없어 MTTR 을 산출하지 못했다"
        )
    if unparsed_events:
        excluded.append(
            f"occurred_at 을 해석하지 못한 에러 이력 {unparsed_events}건은 집계에서 제외했다"
        )
    excluded.append(
        "repair_records 에 수리 시각 컬럼이 없어 window_months 로 자를 수 없다 — "
        "MTTR·예방보전 비율·누적 수리비는 전 기간 집계다"
    )

    availability = (
        None
        if mtbf_days is None or mttr_hours is None
        else mtbf_days / (mtbf_days + mttr_hours / HOURS_PER_DAY)
    )

    planned = sum(1 for r in signed if r["work_type"] == "PLANNED")
    unplanned = sum(1 for r in signed if r["work_type"] == "UNPLANNED")
    planned_ratio = planned / (planned + unplanned) if (planned + unplanned) else None
    if planned_ratio is None:
        excluded.append("서명된 수리 레코드가 없어 예방보전 비율을 산출하지 못했다")

    asset = con.execute(
        "SELECT acquisition_cost, cumulative_repair_cost FROM assets WHERE asset_id = ?",
        (asset_id,),
    ).fetchone()
    acquisition_cost = asset["acquisition_cost"] if asset else None
    cumulative = (asset["cumulative_repair_cost"] if asset else None) or 0
    ratio = cumulative / acquisition_cost if acquisition_cost else None

    if not equipment_ids:
        excluded.append(
            f"{asset_id} 에 연결된 설비(equipment)가 없어 이력 기반 지표를 산출하지 못했다"
        )
    return {
        "window_months": METRICS_WINDOW_MONTHS,
        "mtbf_days": None if mtbf_days is None else round(mtbf_days, 1),
        "mtbf_basis": MTBF_BASIS,  # D70 — 가동시간 기준이 아님을 필드로 고지
        "mttr_hours": None if mttr_hours is None else round(mttr_hours, 2),
        "availability": None if availability is None else round(availability, 4),
        "planned_ratio": None if planned_ratio is None else round(planned_ratio, 3),
        "n_repairs_signed": len(signed),
        "n_repairs_unsigned": unsigned_n,
        "acquisition_cost": acquisition_cost,
        "cumulative_repair_cost": cumulative,
        "cumulative_repair_ratio": None if ratio is None else round(ratio, 3),
        "excluded": excluded,
        # D65 — 매수자에게 나가는 문서에서 이 고지가 빠지면 null 이 '양호'로 읽힌다
        "disclaimer": METRICS_DISCLAIMER,
    }


def _repair_history(con: sqlite3.Connection, asset_id: str) -> tuple[list[dict], list[dict]]:
    """(정비 이력 요약, 핵심부품 갱신 내역) — **`signed_at IS NOT NULL` 만** (`12 §11`).

    서명되지 않은 레코드를 증빙에 실으면 매수자가 검증할 수 없는 주장이 증빙 패키지에 들어간다.
    """
    rows = con.execute(
        "SELECT r.repair_id, r.equipment_id, r.work_type, r.expenditure_class, r.cost,"
        " r.downtime_hours, r.parts, r.part_class, r.signed_at, r.performed_by, r.verified_by"
        " FROM repair_records r JOIN equipment e ON e.equipment_id = r.equipment_id"
        " WHERE e.asset_id = ? AND r.signed_at IS NOT NULL"
        " ORDER BY r.signed_at DESC, r.repair_id DESC",
        (asset_id,),
    ).fetchall()

    critical_parts = {
        r["part_no"] for r in con.execute("SELECT part_no FROM parts WHERE part_class='CRITICAL'")
    }
    history: list[dict] = []
    renewals: list[dict] = []
    for r in rows:
        parts = json.loads(r["parts"] or "[]")
        item = {
            "repair_id": r["repair_id"],
            "equipment_id": r["equipment_id"],
            "work_type": r["work_type"],
            "expenditure_class": r["expenditure_class"],
            "cost": r["cost"],
            "downtime_hours": r["downtime_hours"],
            "parts": parts,
            "signed_at": iso_utc(r["signed_at"]),
            "performed_by": r["performed_by"],
            "verified_by": r["verified_by"],
        }
        history.append(item)
        hits = [p for p in parts if p in critical_parts]
        if hits:
            # `12 §8` — 핵심부품 갱신 내역은 **가격에 직접 영향**을 주므로 별도 절로 뽑는다.
            renewals.append(
                {
                    "repair_id": r["repair_id"],
                    "equipment_id": r["equipment_id"],
                    "parts": hits,
                    "signed_at": iso_utc(r["signed_at"]),
                    "cost": r["cost"],
                }
            )
    return history, renewals


def render_documents(bundle: dict, con: sqlite3.Connection, *, asset_id: str) -> dict:
    """처분 승인서 · 진술보장서 · 증빙 패키지(축소판)를 **저장하지 않고** 렌더한다 (D86).

    D57 선례(`print_page` 를 저장하지 않고 응답 조립 시점 계산)와 같은 구조다. 저장하면
    템플릿·산식이 바뀔 때 저장본이 조용히 낡는다. 다만 *고정되지 않는다는 사실을 숨기면*
    계층 3의 존재 이유가 무너지므로 `hash_fixed:false` 와 `missing_sections` 를 강제한다.

    ⛔ 문안을 LLM 이 생성하지 않는다 — 템플릿은 코드이고 번들·DB 의 값만 채운다.
    """
    asset = con.execute(
        "SELECT asset_id, name, category, acquired_at, book_value, acquisition_cost"
        " FROM assets WHERE asset_id = ?",
        (asset_id,),
    ).fetchone()
    facts = bundle.get("facts") or {}
    mode = facts.get("disposal_mode") or "SALE"
    texts = _rule_texts(bundle, con)

    # 4버킷을 번들의 `evaluated[]` 에서 되짚는다 — 저장된 번들이 정본이고, 지금 다시 판정한
    # 결과가 아니다(그건 서명 경계에서만 한다). `disposal_type` 은 룰 본문에서 온다.
    fired: dict[str, list[dict]] = {"blockers": [], "preconditions": [], "holds": [], "insufficient": []}
    for e in bundle.get("evaluated") or []:
        meta = texts.get((e.get("rule_id"), e.get("rule_version")))
        if meta is None:
            continue
        entry = {
            "rule_id": e["rule_id"],
            "rule_version": e["rule_version"],
            "label": meta["label"],
            "message": meta["message"],
            "resolve_options": meta["resolve_options"],
            "law_refs": meta["law_refs"],
            "requires_expert_review": meta["requires_expert_review"],
        }
        if e.get("verdict") == "TRIGGERED" and meta["disposal_type"] == "BLOCKING":
            fired["blockers"].append(entry)
        elif e.get("verdict") == "TRIGGERED" and meta["disposal_type"] == "PRECONDITION":
            fired["preconditions"].append(entry)
        elif e.get("verdict") == "HOLD":
            fired["holds"].append(entry)
        elif e.get("verdict") == "INSUFFICIENT_FACTS":
            fired["insufficient"].append(entry)

    history, renewals = _repair_history(con, asset_id)

    return {
        # ── ① 처분 승인서
        "approval": {
            "title": "설비 자산 처분 승인서",
            "asset": {
                "asset_id": asset_id,
                "name": asset["name"] if asset else None,
                "category": asset["category"] if asset else None,
                "acquired_at": asset["acquired_at"] if asset else None,
                "book_value": asset["book_value"] if asset else None,
            },
            "disposal_mode": mode,
            "disposal_mode_label": DISPOSAL_MODE_LABELS.get(mode, mode),
            "disposal_date": facts.get("disposal_date"),
            "blockers": fired["blockers"],
            "preconditions": fired["preconditions"],
            "holds": fired["holds"],
            "insufficient": fired["insufficient"],
            "law_footnotes": _law_footnotes(bundle, con),
        },
        # ── ② 진술보장서 — 룰별 진술 항목 + 계약 근거의 `hash_fixed:false`
        "representation_warranty": {
            "title": "진술 및 보장서",
            "statements": [
                {
                    "rule_id": rid,
                    "rule_version": ver,
                    "label": meta["label"],
                    "statement": meta["interpretation"],
                    "confidence": meta["confidence"],
                    "requires_expert_review": meta["requires_expert_review"],
                    "law_refs": meta["law_refs"],
                }
                for (rid, ver), meta in sorted(texts.items(), key=lambda kv: str(kv[0]))
            ],
            "contracts": list(bundle.get("contracts") or []),
        },
        # ── ③ 증빙 패키지(축소판) — `12 §8` 4종 중 3종
        "evidence_package": {
            "title": "처분 증빙 패키지 (축소판)",
            "maintenance_history": history,
            "metrics": _metrics(con, asset_id),
            "critical_parts_renewal": renewals,
        },
        # ── D86 강제 고지 2종
        "missing_sections": list(MISSING_SECTIONS),
        "hash_fixed": False,
        "hash_fixed_note": HASH_FIXED_NOTE,
        "unreviewed_template_notice": "문서 문안은 미검수 초안이다 (TODO_직접할일.md)",
    }


# ── 상태 전이 ───────────────────────────────────────────────────────────────────
def _locked_row(con: sqlite3.Connection, decision_id: str) -> sqlite3.Row:
    r = con.execute(
        "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
    ).fetchone()
    if r is None:
        raise KeyError(decision_id)  # → 404
    return r


def submit(decision_id: str, *, requested_by: str, db_path: Path | None = None) -> dict:
    """draft → pending. 정비사의 '팀장 승인 요청' (A3 — 에이전트 루프 밖).

    신원 stamp 를 여기서 한다 (D23·D37) — 도구는 `requested_by` 를 채우지 않는다.
    이미 stamp 돼 있으면 덮지 않는다: 요청자를 나중에 바꿀 수 있으면 감사 추적이 무너진다.
    """
    with connect(db_path) as con:
        row = _locked_row(con, decision_id)
        if row["state"] != ALLOWED_FROM["pending"]:
            raise DecisionTransitionError(decision_id, row["state"], "pending")
        con.execute(
            "UPDATE decisions SET state='pending',"
            " requested_by = COALESCE(requested_by, ?) WHERE decision_id = ?",
            (requested_by, decision_id),
        )
    return get_decision(decision_id, db_path) or {}


def reject(
    decision_id: str, *, reviewed_by: str, reason: str, db_path: Path | None = None
) -> dict:
    """pending → rejected. 사유 필수 (D38) — 라우터의 pydantic 이 공백을 먼저 막는다."""
    with connect(db_path) as con:
        row = _locked_row(con, decision_id)
        if row["state"] != ALLOWED_FROM["rejected"]:
            raise DecisionTransitionError(decision_id, row["state"], "rejected")
        con.execute(
            "UPDATE decisions SET state='rejected', reviewed_by=?, decision_note=?"
            " WHERE decision_id = ?",
            (reviewed_by, reason, decision_id),
        )
    return get_decision(decision_id, db_path) or {}


def sign(
    decision_id: str,
    *,
    reviewed_by: str,
    override: bool = False,
    override_reason: str | None = None,
    note: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """pending → signed. **순서가 계약이다** (모듈 docstring ①~⑥ · D84).

    반환은 `get_decision()` 형태. 실패는 예외로 올리고 라우터가 HTTP 로 매핑한다 —
    이건 사람용 REST 라 D9(도구는 status 로 반환)의 대상이 아니다.
    """
    with connect(db_path) as con:
        # ① 존재
        row = _locked_row(con, decision_id)

        # ② 전이 가능 상태인가 (이미 signed 인 건 재서명 → 409)
        if row["state"] != ALLOWED_FROM["signed"]:
            raise DecisionTransitionError(decision_id, row["state"], "signed")

        # ③ 근거 재산출·해시 대조. **override 판정보다 먼저다** (D84)
        stored = _stored_bundle(row)
        mode, disposal_date = _replay_args(stored)
        try:
            _bundle, recomputed_hash, judgment = rebuild_bundle(
                con, row["asset_id"], mode, disposal_date
            )
        except KeyError as exc:  # 자산 행이 사라졌다
            raise EvidenceChanged(
                decision_id, row["bundle_hash"], "", f"자산 행이 존재하지 않습니다: {row['asset_id']}"
            ) from exc
        if recomputed_hash != row["bundle_hash"]:
            raise EvidenceChanged(decision_id, row["bundle_hash"], recomputed_hash)

        # ④ 차단 판정에 override 없이 서명하려는 시도
        verdict = judgment["verdict"]
        if verdict in BLOCKING_VERDICTS and override is not True:
            raise OverrideRequired(decision_id, verdict, judgment)

        # ⑤ override 사유 게이트 (DB CHECK 가 2차 방어선 — D63)
        if override is True and not (override_reason or "").strip():
            raise OverrideReasonRequired(decision_id)

        # ⑥ 확정. `verdict_at_signing` 은 **재산출 값**으로 덮는다 (컬럼 이름이 말하는 것)
        con.execute(
            "UPDATE decisions SET state='signed', signed_at=?, reviewed_by=?,"
            " override=?, override_reason=?, verdict_at_signing=?,"
            " decision_note=COALESCE(?, decision_note) WHERE decision_id = ?",
            (
                now_utc_sql(),
                reviewed_by,
                1 if override else 0,
                (override_reason or "").strip() or None if override else None,
                verdict,
                note,
                decision_id,
            ),
        )
    return get_decision(decision_id, db_path) or {}
