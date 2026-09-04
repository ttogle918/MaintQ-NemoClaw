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

from data.dbcompat import DbConnection, DbRow

import json
from datetime import datetime, timezone
from typing import Any

from backend.db import connect
from backend.services.disposal import RuleCatalogError, _load_catalog, read_only
from backend.services.po import iso_utc
from backend.services import state_machine
import data.doc_review as _doc_review  # D73 — 공유 데이터 계층 (mcp_server 와 같은 문구를 읽는다)
from data import maint_value  # D73·D101 — 보전지표 산식의 단일 출처 (MQ-908 위임)
from data import txn
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

# ⛔ 보전지표 산식 상수를 여기 두지 않는다 (MQ-908) — `_metrics()` 가
# `data.maint_value.maintenance_metrics()` 로 위임하므로 산식·상수의 정본은 그 모듈
# 한 곳뿐이다. 예전에는 이 파일이 `HOURS_PER_DAY`·`MTBF_BASIS`·`METRICS_WINDOW_MONTHS`·
# `METRICS_DISCLAIMER` 사본을 갖고 회귀(⑳)로 드리프트를 잡았지만, 위임 후에는 사본이
# 아예 없으므로 드리프트 자체가 구조적으로 불가능하다.


# ── 예외 (라우터가 HTTP 로 매핑한다. D38 — 403/409/422 를 섞지 않는다) ───────────
class DecisionTransitionError(Exception):
    """현재 상태에서 할 수 없는 전이 → 409."""

    def __init__(self, decision_id: str, current: str, target: str) -> None:
        self.decision_id, self.current, self.target = decision_id, current, target
        super().__init__(
            f"{decision_id} 는 지금 '{current}' 상태라 '{target}' 로 전이할 수 없습니다 "
            f"('{ALLOWED_FROM[target]}' 에서만 가능)"
        )


#: 전이 골격(연결·잠금·404·409)은 `state_machine.Flow` 가 소유한다 (D126).
FLOW = state_machine.Flow("decisions", "decision_id", ALLOWED_FROM, DecisionTransitionError)


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
    con: DbConnection, asset_id: str, disposal_mode: str, disposal_date: str | None
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


def _stored_bundle(row: DbRow) -> dict:
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


def _row_to_decision(r: DbRow, *, with_bundle: bool = False) -> dict:
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


def list_decisions(state: str | None = None, db_path: str | None = None) -> list[dict]:
    sql = _DECISION_SELECT
    args: list[object] = []
    if state:
        sql += " WHERE d.state = ?"
        args.append(state)
    sql += " ORDER BY d.created_at DESC, d.decision_id DESC"
    with read_only(db_path) as con:
        return [_row_to_decision(r) for r in con.execute(sql, args).fetchall()]


def get_decision_identity(decision_id: str, db_path: str | None = None) -> dict | None:
    """docx 다운로드가 얹을 신원·서명 값 (D23·D37·D81).

    `data/doc_fields.py` 는 이 자리를 **만들지 않는다** — 여기서만 DB 에서 읽는다.
    서명자는 `signed_by` 가 아니라 **`reviewed_by`** 다(`05_DB_SCHEMA §12`).
    부서는 `users` 에 조인해 가져온다.
    """
    with read_only(db_path) as con:
        r = con.execute(
            "SELECT d.decision_id, d.signed_at, d.override, d.override_reason, d.session_id,"
            " rv.display_name AS signed_by_name,"
            " ru.display_name AS requested_by_name, ru.department AS requested_by_department"
            " FROM decisions d"
            " LEFT JOIN users rv ON rv.user_id = d.reviewed_by"
            " LEFT JOIN users ru ON ru.user_id = d.requested_by"
            " WHERE d.decision_id = ?",
            (decision_id,),
        ).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["signed_at"] = iso_utc(d.get("signed_at"))
    return d


def get_decision(decision_id: str, db_path: str | None = None) -> dict | None:
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
def _law_footnotes(bundle: dict, con: DbConnection) -> list[dict]:
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


def _rule_texts(bundle: dict, con: DbConnection) -> dict[tuple[str, int], dict]:
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


# `_metrics()` 가 위임 결과에서 뽑아 쓰는 필드 — **이 순서·이 집합이 옛 `_metrics()` 의
# 반환 계약이다.** `data.maint_value.maintenance_metrics()` 는 이 밖에도 `status`·`asset_id`·
# `mtbf_trend`·`repeat_failure`·`not_considered` 를 더 갖고 있지만(MCP 도구 §11 계약),
# `evidence_package.metrics` 의 반환 형태를 한 글자도 바꾸지 않기 위해 여기서 부분집합만
# 옮긴다(MQ-908). 늘리려면 `render_documents` 소비 측과 `spikes/approvals_contract.py` ⑳
# 대조 목록을 같은 커밋에서 함께 봐야 한다.
_METRICS_KEYS: tuple[str, ...] = (
    "window_months",
    "mtbf_days",
    "mtbf_basis",
    "mttr_hours",
    "availability",
    "planned_ratio",
    "n_repairs_signed",
    "n_repairs_unsigned",
    "acquisition_cost",
    "cumulative_repair_cost",
    "cumulative_repair_ratio",
    "excluded",
    "disclaimer",
)


def _metrics(con: DbConnection, asset_id: str) -> dict:
    """보전지표 — **`data.maint_value.maintenance_metrics()` 로 전량 위임한다** (MQ-908).

    이 함수는 예전에 `get_maintenance_metrics`(`04 §11`)와 같은 산식을 backend 에
    **한 벌 더** 갖고 회귀(`spikes/approvals_contract.py` ⑳)로 드리프트를 잡았다. 이제는
    도구(`mcp_server/tools/get_maintenance_metrics.py`)도 이 함수도 **같은 함수**
    (`data.maint_value.maintenance_metrics`)를 호출한다 — 산식·상수의 정본은 그 모듈
    한 곳뿐이고, 드리프트는 회귀가 아니라 구조로 불가능하다(⑳ 은 그 사실을 계속 확인한다).

    반환은 위임 결과의 **부분집합**이다(`_METRICS_KEYS`) — `evidence_package.metrics`
    의 형태를 한 글자도 바꾸지 않기 위해서다. `status`·`asset_id`·`mtbf_trend`·
    `repeat_failure`·`not_considered` 는 도구 계약(`04 §11`)에는 있지만 이 자리에는
    싣지 않는다.
    """
    result = maint_value.maintenance_metrics(con, asset_id=asset_id)
    if result.get("status") != "ok":
        # `get_decision()` 은 `assets` 와 INNER JOIN 된 결정 행에서 얻은 asset_id 만 넘긴다 —
        # 자산이 존재하지 않는 경로가 없으므로 실패는 불변식 위반이다. 조용히 삼키면
        # 증빙 패키지에 "판단 근거 부족"이 아니라 근거 자체가 빠진 채로 나간다.
        raise RuntimeError(
            f"보전지표 위임 호출이 실패했습니다({asset_id}): "
            f"{result.get('reason')} — {result.get('message')}"
        )
    return {key: result[key] for key in _METRICS_KEYS}


def _repair_history(con: DbConnection, asset_id: str) -> tuple[list[dict], list[dict]]:
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
        # parts 원소는 두 형태가 섞여 있다 — 옛 시드 데이터는 순수 문자열
        # (data/seed.py), 실제 create_repair_record 도구는 {"part_no": "..."} 객체를
        # 저장한다(mcp_server/tools/create_repair_record.py). Postgres 마이그레이션과
        # 무관한 기존 버그(문자열만 가정해 `p in critical_parts` 가 dict 에서
        # unhashable 로 죽는다)를 이번에 처음 실제로 밟아 발견했다 — 두 형태를 모두
        # 받아들이도록 최소 방어만 추가한다.
        part_nos = [p if isinstance(p, str) else p.get("part_no") for p in parts]
        hits = [p for p in part_nos if p in critical_parts]
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


def render_documents(bundle: dict, con: DbConnection, *, asset_id: str) -> dict:
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
        # ⛔ 리터럴 금지 — mcp_server 쪽과 **같은 값**이어야 한다 (D73 공유 계층, D90)
        # 불리언을 함께 싣는 이유: UI 가 문구를 파싱해 톤을 정하면 문구가 바뀔 때 조용히
        # 어긋난다. 상태→표시 매핑은 상태값으로 한다 (D87).
        "template_reviewed": _doc_review.TEMPLATE_REVIEWED,
        "template_review_notice": _doc_review.template_review_notice(),
    }


# ── 상태 전이 ───────────────────────────────────────────────────────────────────
def _locked_row(con: DbConnection, decision_id: str) -> DbRow:
    """전이 대상 행을 **실제로 잠근 채** 읽는다 (D126, → 404 는 KeyError).

    이전 구현은 이 이름을 달고도 평범한 SELECT 였다 — 두 결재자가 동시에 서명/반려하면
    둘 다 통과했다. 잠금 구현은 `data/txn.py` 한 곳이 소유한다."""
    return txn.locked_row(con, "decisions", "decision_id", decision_id)


class NotEditableError(Exception):
    """draft 가 아닌 결정을 수정하려 함 → 409. `services/po`·`services/repairs` 와 같은 패턴."""

    def __init__(self, decision_id: str, state: str) -> None:
        super().__init__(
            f"{decision_id} 는 지금 '{state}' 상태라 수정할 수 없습니다 (draft 만 수정 가능)"
        )


def _next_decision_id(con: DbConnection) -> str:
    """`DEC-%04d` 채번. 경쟁 없는 발급은 `data/txn.py` 가 소유한다 (D126) —
    `mcp_server/tools/generate_disposal_document.py` 도 같은 함수를 쓴다."""
    return txn.next_sequential_id(con, "decisions", "decision_id", "DEC")


def _adjudicate(
    con: DbConnection, *, asset_id: str, disposal_mode: str, disposal_date: str | None
) -> tuple[dict, str, str]:
    """재판정 — `(bundle, bundle_hash, verdict)`.

    `sign()` 이 서명 시점에 하는 일(③ 근거 재산출·해시 대조)과 **같은 함수**를 쓴다
    (`rebuild_bundle`). 화면 경로가 독자적인 판정 로직을 갖지 않는다는 뜻이다 —
    갈리면 "화면에서 본 판정"과 "서명 때 나온 판정"이 달라진다.
    """
    bundle, bundle_hash, judgment = rebuild_bundle(con, asset_id, disposal_mode, disposal_date)
    return bundle, bundle_hash, judgment["verdict"]


def create(
    *,
    asset_id: str,
    disposal_mode: str,
    disposal_date: str | None,
    reason: str,
    requested_by: str,
    db_path: str | None = None,
) -> dict:
    """화면이 처분 초안을 **직접 생성**한다 (P39 — D111 이 발주서에 연 경로의 확장).

    ⛔ **D10 대상이 아니다.** MCP 도구가 아니라 백엔드 쓰기다(D111 이 정리한 경계).
    판정은 `generate_disposal_document`(MCP)와 **같은 `rebuild_bundle()`** 을 지난다.

    ⛔ **D63 — BLOCKED 여도 막지 않는다.** 차단 사실이 초안에 기록된 채 결재에 올라가고,
    예외 적용은 서명 화면에서만 한다(D81). 그래서 `override`·`override_reason`·
    `reviewed_by` 는 이 함수의 파라미터가 **아니다**.
    """
    if not (reason or "").strip():
        return {"status": "error", "reason": "reason_required", "message": "처분 사유는 필수입니다 (D5)."}
    with connect(db_path) as con:
        bundle, bundle_hash, verdict = _adjudicate(
            con, asset_id=asset_id, disposal_mode=disposal_mode, disposal_date=disposal_date
        )
        decision_id = _next_decision_id(con)
        con.execute(
            "INSERT INTO decisions (decision_id, asset_id, decision_type, evidence_bundle,"
            " bundle_hash, verdict_at_signing, override, override_reason, reviewed_by,"
            " signed_at, state, reason, requested_by)"
            " VALUES (?,?,'DISPOSAL',?,?,?, false, NULL, NULL, NULL, 'draft', ?, ?)",
            (
                decision_id,
                asset_id,
                canonical_json(bundle),
                bundle_hash,
                verdict,
                reason.strip(),
                requested_by,
            ),
        )
    return get_decision(decision_id, db_path) or {}


def update(
    decision_id: str,
    *,
    asset_id: str,
    disposal_mode: str,
    disposal_date: str | None,
    reason: str,
    db_path: str | None = None,
) -> dict:
    """draft 상태 처분 초안을 수정한다. draft 가 아니면 `NotEditableError` → 409.

    🔴 **처분에만 있는 문제 — 수정은 재판정을 부른다.** `disposal_mode`·`disposal_date` 는
    룰 입력이라 바뀌면 판정도 근거 번들도 달라진다. 그래서 `evidence_bundle`·`bundle_hash`·
    `verdict_at_signing` 을 **새 값으로 덮는다** — 발주의 `unit_price`, 수리의
    `expenditure_class` 재산출과 같은 자리다.

    이것이 안전한 이유: `sign()` 이 서명 시점에 **다시** 재산출·대조한다(D84). 수정으로
    해시가 바뀌어도 서명 게이트는 그대로 산다. `verdict_at_signing` 을 재산출 값으로 덮는
    것도 `sign()` 이 이미 하는 일이다 — 이 함수는 그걸 draft 단계에서 할 뿐이다.

    ⛔ 서명 필드(`override`·`override_reason`·`reviewed_by`·`signed_at`)는 SET 절에 없다.
    """
    if not (reason or "").strip():
        return {"status": "error", "reason": "reason_required", "message": "처분 사유는 필수입니다 (D5)."}
    with connect(db_path) as con:
        row = _locked_row(con, decision_id)
        if row["state"] != "draft":
            raise NotEditableError(decision_id, row["state"])
        bundle, bundle_hash, verdict = _adjudicate(
            con, asset_id=asset_id, disposal_mode=disposal_mode, disposal_date=disposal_date
        )
        con.execute(
            "UPDATE decisions SET asset_id=?, evidence_bundle=?, bundle_hash=?,"
            " verdict_at_signing=?, reason=? WHERE decision_id=? AND state='draft'",
            (asset_id, canonical_json(bundle), bundle_hash, verdict, reason.strip(), decision_id),
        )
    return get_decision(decision_id, db_path) or {}


def submit(decision_id: str, *, requested_by: str, db_path: str | None = None) -> dict:
    """draft → pending. 정비사의 '팀장 승인 요청' (A3 — 에이전트 루프 밖).

    신원 stamp 를 여기서 한다 (D23·D37) — 도구는 `requested_by` 를 채우지 않는다.
    이미 stamp 돼 있으면 덮지 않는다: 요청자를 나중에 바꿀 수 있으면 감사 추적이 무너진다.
    """
    with FLOW.transition(decision_id, "pending", db_path=db_path) as (con, _row):
        con.execute(
            "UPDATE decisions SET state='pending',"
            " requested_by = COALESCE(requested_by, ?) WHERE decision_id = ?",
            (requested_by, decision_id),
        )
    return get_decision(decision_id, db_path) or {}


def reject(
    decision_id: str, *, reviewed_by: str, reason: str, db_path: str | None = None
) -> dict:
    """pending → rejected. 사유 필수 (D38) — 라우터의 pydantic 이 공백을 먼저 막는다."""
    with FLOW.transition(decision_id, "rejected", db_path=db_path) as (con, _row):
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
    db_path: str | None = None,
) -> dict:
    """pending → signed. **순서가 계약이다** (모듈 docstring ①~⑥ · D84).

    반환은 `get_decision()` 형태. 실패는 예외로 올리고 라우터가 HTTP 로 매핑한다 —
    이건 사람용 REST 라 D9(도구는 status 로 반환)의 대상이 아니다.
    """
    # ①존재 ②전이 가능 상태 — 골격은 `state_machine.Flow` 가 소유한다 (D126).
    # ③~⑥ 은 이 흐름 고유의 계약이라 여기 그대로 남는다 (D84 — 순서가 계약이다).
    with FLOW.transition(decision_id, "signed", db_path=db_path) as (con, row):
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
