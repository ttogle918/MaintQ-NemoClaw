"""
룰 평가 엔진 — 계층 1(법령 스냅샷) · 계층 2(해석 룰) 사이의 결정론적 판정기.

설계 원칙:
  1. LLM은 이 엔진을 호출할 뿐, 판정을 직접 만들지 않는다.
  2. 근거(law_refs 또는 contract_refs)가 없는 룰은 로드 자체가 거부된다 (D61).
  3. 경계 구간(boundary.review_band)은 단정하지 않고 HOLD를 반환한다 (D62).
"""

from __future__ import annotations

from data.dbcompat import DbConnection, DbRow

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent
RULES_DIR = BASE / "rules"
LAWS_DIR = BASE / "laws"


# ---------------------------------------------------------------- 계층 1


def normalize(text: str) -> str:
    """해시 산출 전 정규화. 전각/반각·공백 변형으로 해시가 흔들리는 것을 막는다."""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.split())


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(normalize(text).encode()).hexdigest()


@dataclass
class LawRef:
    law_ref_id: str
    law_name: str
    article: str
    title: str
    text: str | None
    fetch_status: str
    effective_from: str | None
    effective_to: str | None
    source_url: str
    text_hash: str | None
    verification_note: str | None = None

    @property
    def is_fetched(self) -> bool:
        return self.fetch_status == "FETCHED" and self.text is not None

    def citation(self) -> str:
        return f"{self.law_name} 제{self.article}조({self.title})"


def load_laws() -> dict[str, LawRef]:
    laws: dict[str, LawRef] = {}
    for path in sorted(LAWS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        laws[raw["law_ref_id"]] = LawRef(
            law_ref_id=raw["law_ref_id"],
            law_name=raw["law_name"],
            article=raw["article"],
            title=raw["title"],
            text=raw.get("text"),
            fetch_status=raw.get("fetch_status", "PENDING"),
            effective_from=raw.get("effective_from"),
            effective_to=raw.get("effective_to"),
            source_url=raw.get("source_url", ""),
            text_hash=raw.get("text_hash"),
            verification_note=raw.get("verification_note"),
        )
    return laws


LAW_COLUMNS = (
    "law_ref_id",
    "law_name",
    "article",
    "title",
    "text",
    "fetch_status",
    "effective_from",
    "effective_to",
    "source_url",
    "text_hash",
    "verification_note",
)


def load_laws_from_db(con: DbConnection) -> dict[str, LawRef]:
    """계층 1 **사본**을 DB에서 읽는다. 정본은 `data/rules/laws/*.json` 이다 (D60).

    파일 로더(`load_laws`)와 같은 dataclass 를 만든다 — 두 경로가 어긋나면
    `spikes/rules_db_load.py` ⓐ 가 잡는다. `source_url` 이 NULL 인 행은
    파일 로더의 기본값(`""`)과 맞춘다.
    """
    sql = f"SELECT {', '.join(LAW_COLUMNS)} FROM law_refs ORDER BY law_ref_id"  # noqa: S608
    laws: dict[str, LawRef] = {}
    for row in con.execute(sql).fetchall():
        raw = dict(zip(LAW_COLUMNS, row))
        laws[raw["law_ref_id"]] = LawRef(
            law_ref_id=raw["law_ref_id"],
            law_name=raw["law_name"],
            article=raw["article"],
            title=raw["title"],
            text=raw["text"],
            fetch_status=raw["fetch_status"] or "PENDING",
            effective_from=raw["effective_from"],
            effective_to=raw["effective_to"],
            source_url=raw["source_url"] or "",
            text_hash=raw["text_hash"],
            verification_note=raw["verification_note"],
        )
    return laws


def get_law_as_of(laws: dict[str, LawRef], law_ref_id: str, at: date) -> LawRef:
    """시점 기준 조회. 해당 시점 조문이 없으면 조용히 최신본을 주지 않고 예외."""
    law = laws.get(law_ref_id)
    if law is None:
        raise KeyError(f"미등록 법령 참조: {law_ref_id}")
    if law.effective_from and date.fromisoformat(law.effective_from) > at:
        raise ValueError(f"{law_ref_id}: {at} 시점에 시행 전인 조문")
    if law.effective_to and date.fromisoformat(law.effective_to) <= at:
        raise ValueError(f"{law_ref_id}: {at} 시점에 이미 실효된 조문")
    return law


# ---------------------------------------------------------------- 계층 2


class RuleIntegrityError(Exception):
    """근거 없는 룰은 존재할 수 없다 (D61)."""


@dataclass
class Rule:
    rule_id: str
    label: str
    category: str
    disposal_type: str  # BLOCKING | PRECONDITION | AUTO_CLOSE
    source_type: str  # LAW | CONTRACT
    law_refs: list[str]
    contract_refs: list[str]
    interpretation: str
    required_facts: list[str]
    trigger: dict[str, Any]
    boundary: dict[str, Any] | None
    message: str
    resolve_options: list[str]
    confidence: str
    requires_expert_review: bool
    rule_version: int


def load_rules(laws: dict[str, LawRef]) -> dict[str, Rule]:
    rules: dict[str, Rule] = {}
    for path in sorted(RULES_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        law_refs = raw.get("law_refs", [])
        contract_refs = raw.get("contract_refs", [])

        # 근거 없는 룰은 로드 거부 — 계층 2의 핵심 불변식 (D61)
        if not law_refs and not contract_refs:
            raise RuleIntegrityError(f"{raw['rule_id']}: 근거 참조 없음")
        for ref in law_refs:
            if ref not in laws:
                raise RuleIntegrityError(f"{raw['rule_id']}: 미등록 법령 참조 {ref}")

        rules[raw["rule_id"]] = Rule(
            rule_id=raw["rule_id"],
            label=raw["label"],
            category=raw["category"],
            disposal_type=raw["disposal_type"],
            source_type=raw["source_type"],
            law_refs=law_refs,
            contract_refs=contract_refs,
            interpretation=raw["interpretation"],
            required_facts=raw.get("required_facts", []),
            trigger=raw["trigger"],
            boundary=raw.get("boundary"),
            message=raw["message"],
            resolve_options=raw.get("resolve_options", []),
            confidence=raw.get("confidence", "MEDIUM"),
            requires_expert_review=raw.get("requires_expert_review", False),
            rule_version=raw.get("rule_version", 1),
        )
    return rules


RULE_COLUMNS = (
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


def _json_col(rule_id: str, column: str, value: str | None, default: Any) -> Any:
    """DB의 JSON 컬럼 파싱. 깨진 JSON을 조용히 기본값으로 넘기지 않는다."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuleIntegrityError(f"{rule_id}: {column} JSON 파싱 실패 — {exc}") from exc


def load_rules_from_db(con: DbConnection, laws: dict[str, LawRef]) -> dict[str, Rule]:
    """계층 2 **사본**을 DB에서 읽는다. 정본은 `data/rules/rules/*.json` 이다 (D60).

    ★ 파일 로더(`load_rules`)와 **완전히 같은 불변식**을 적용한다 — 근거 없는 룰 거부(D61),
      미등록 법령 참조 거부. DB 사본이 무결성 검사를 우회하는 경로가 되면
      `seed_rule_catalog` 가 `load_rules` 를 경유하도록 만든 게이트가 무의미해진다.

    `(rule_id, rule_version)` 복합 PK 라 같은 룰의 여러 개정본이 공존할 수 있다 (D60).
    판정에는 **rule_id 별 최신 버전 1행만** 쓴다 — 구 버전은 서명 시점 재현용으로 남는다.
    """
    sql = (  # noqa: S608
        f"SELECT {', '.join('r.' + c for c in RULE_COLUMNS)} FROM rules r"
        " JOIN (SELECT rule_id, MAX(rule_version) AS v FROM rules GROUP BY rule_id) m"
        " ON m.rule_id = r.rule_id AND m.v = r.rule_version"
        " ORDER BY r.rule_id"
    )
    rules: dict[str, Rule] = {}
    for row in con.execute(sql).fetchall():
        raw = dict(zip(RULE_COLUMNS, row))
        rule_id = raw["rule_id"]
        law_refs = _json_col(rule_id, "law_refs", raw["law_refs"], [])
        contract_refs = _json_col(rule_id, "contract_refs", raw["contract_refs"], [])

        # 파일 로더 127~131행과 같은 게이트 (D61)
        if not law_refs and not contract_refs:
            raise RuleIntegrityError(f"{rule_id}: 근거 참조 없음")
        for ref in law_refs:
            if ref not in laws:
                raise RuleIntegrityError(f"{rule_id}: 미등록 법령 참조 {ref}")

        # 필수 컬럼 NULL 거부 — 파일 로더는 raw["trigger"] 로 KeyError 를 내는데
        # DB 로더는 _json_col 이 기본값 None 을 돌려주어 **조용히 통과**하던 구멍이었다.
        # 실 스키마에는 NOT NULL 이 걸려 있으나 CHECK 없는 ERP 사본에서는 뚫리고,
        # 그때 터지는 곳은 로드 시점이 아니라 _eval_trigger 의 TypeError 다 —
        # D61 이 "로드 단계에서 막는다"고 한 지점보다 훨씬 뒤다.
        for col in ("label", "message", "trigger"):
            if raw[col] is None:
                raise RuleIntegrityError(f"{rule_id}: 필수 컬럼 {col} 이 NULL")

        rules[rule_id] = Rule(
            rule_id=rule_id,
            label=raw["label"],
            category=raw["category"],
            disposal_type=raw["disposal_type"],
            source_type=raw["source_type"],
            law_refs=law_refs,
            contract_refs=contract_refs,
            interpretation=raw["interpretation"],
            required_facts=_json_col(rule_id, "required_facts", raw["required_facts"], []),
            trigger=_json_col(rule_id, "trigger", raw["trigger"], None),
            boundary=_json_col(rule_id, "boundary", raw["boundary"], None),
            message=raw["message"],
            resolve_options=_json_col(rule_id, "resolve_options", raw["resolve_options"], []),
            confidence=raw["confidence"] or "MEDIUM",
            requires_expert_review=bool(raw["requires_expert_review"]),
            rule_version=raw["rule_version"],
        )
    return rules


# ---------------------------------------------------------------- 사실 조립

# `assets` 에서 그대로 옮겨오는 법정 조건 사실 (11 §7 · D68).
# 여기에 없는 컬럼은 facts 에 들어가지 않는다 — 룰이 읽지 않는 값을 섞으면
# "이 판정이 무엇을 봤는가"가 흐려진다.
ASSET_FACT_COLUMNS = (
    "asset_id",
    "building_id",
    "status",
    "acquired_at",
    "tax_credit_applied",
    "has_lien",
    "lien_creditor",
    "lien_consent_ref",
    "insured",  # D78 — 부보 여부. policy_id 는 증권 식별자일 뿐 판정 근거가 아니다
    "policy_id",
    "safety_inspection_target",
    "last_inspection_date",
    "inspection_valid_until",
)

# SQLite BOOLEAN 은 0/1 정수로 돌아온다. 룰의 `eq true` 와 맞추려면 bool 로 캐스팅해야 한다.
_BOOL_FACT_COLUMNS = frozenset(
    {"tax_credit_applied", "has_lien", "insured", "safety_inspection_target"}
)

# 날짜 사실. **판독 불가하면 키를 만들지 않는다** (아래 build_facts docstring 참조)
_DATE_FACT_COLUMNS = frozenset({"acquired_at", "last_inspection_date", "inspection_valid_until"})

DISPOSAL_MODES = ("SALE", "SCRAP", "TRANSFER")


def _as_date(value: object) -> date | None:
    """ISO 날짜로 읽히지 않으면 None. 판독 실패를 0/오늘로 메우지 않는다 (D62)."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def build_facts(
    asset_row: DbRow | dict,
    *,
    disposal_mode: str | None = None,
    disposal_date: str | None = None,
    at: date | None = None,
) -> dict:
    """`assets` 한 행 → 룰 엔진 facts.

    ★ 가장 중요한 규칙: **값이 None 인 키는 dict 에 넣지 않는다.**
      `evaluate_rule`(216행)이 `f not in facts` 로 사실 누락을 판정하므로, None 을 넣으면
      "모른다"가 "조건 미해당(CLEAR)"으로 조용히 바뀐다 — 불변식 4(D62)가 통째로
      무너지는 단 하나의 지점이다. **False·0 은 값이므로 반드시 포함**한다.
      (반대로 시드가 "해당 없음"을 빈 문자열로 적은 컬럼은 값이 있는 것이다 —
       담보 없는 자산의 `lien_creditor=''` 는 누락이 아니다.)

    파생·판정시점 사실:
      disposal_mode         — 도구 파라미터라 **항상 알 수 있다.** 기본값 'SALE'
      vat_invoice_issued    — precheck 는 **거래 성립 전**이므로 `False` 가 확정 사실이다 (D77).
                              지어낸 값이 아니라 *판정 시점의 정의*다. 발급 여부를 아직 모르는
                              게 아니라, 아직 발급될 수 없는 시점에서 판정하는 것이다.
                              같은 이유로 `sale_amount`·`buyer_biz_no` 같은 **다른 거래 사실은
                              채우지 않는다** — 그건 실제로 모르는 값이고 지어내면 D31 위반이다.
      months_since_acquisition — `acquired_at`·`disposal_date` **둘 다 판독됐을 때만** 계산.
                              ★ 날짜가 ISO 로 읽히지 않으면 **그 원천 키 자체를 빼 버린다.**
                                원천은 남기고 파생만 조용히 건너뛰면 TAX-CREDIT-2Y 가
                                `required_facts`(acquired_at·disposal_date)는 충족한 채
                                `months_since_acquisition` 이 없는 상태로 트리거를 타는데,
                                `lt` 가 `a is not None and a < b` 라 **False → CLEAR** 가 된다.
                                "사실은 충분한데 조건 미해당"이라는 가장 나쁜 형태의 조용한 통과다.
                                키를 빼면 `INSUFFICIENT_FACTS` + `missing_facts` 에 범인이 찍힌다.
                                → 결과적으로 "원천 2개가 facts 에 있으면 파생도 반드시 있다"가
                                  **구조적으로 보장**된다(검사로 막는 게 아니라 만들어질 수 없다).
      risk_grade_before/after · risk_score_delta_pct · risk_grade_changed
                            — 원천이 F6 `risk_profile`(범위 밖). **키를 넣지 않는다.**
                              INSURANCE-NOTIFY 의 경계 검사(`risk_score_delta_pct`)는
                              `facts.get()` 가 None 을 주면 `value is not None` 에서 건너뛰므로
                              예외도 나지 않고 잘못된 HOLD 로도 빠지지 않는다 (실측 확인).

    `at`(판정 기준일)은 파생 필드에 쓰지 않는다 — `disposal_date` 가 없을 때 `at` 으로
    대체하면 "처분일을 모른다"가 조용히 "오늘 처분한다"가 된다 (D62와 같은 유형).
    """
    row = dict(asset_row) if not isinstance(asset_row, dict) else asset_row
    facts: dict[str, Any] = {}

    for col in ASSET_FACT_COLUMNS:
        value = row.get(col)
        if value is None:
            continue  # ★ NULL 은 "모른다" — 키를 만들지 않는다 (D62)
        if col in _DATE_FACT_COLUMNS and _as_date(value) is None:
            continue  # 판독 불가한 날짜는 "모른다"다 — 원문을 남기면 파생 실패가 숨는다
        facts[col] = bool(value) if col in _BOOL_FACT_COLUMNS else value

    facts["disposal_mode"] = disposal_mode or "SALE"
    facts["vat_invoice_issued"] = False

    if disposal_date is not None and _as_date(disposal_date) is not None:
        facts["disposal_date"] = disposal_date
        acquired = _as_date(facts.get("acquired_at"))
        if acquired is not None:
            facts["months_since_acquisition"] = _months_between(acquired, _as_date(disposal_date))

    assert None not in facts.values(), "build_facts 는 None 값 키를 만들지 않는다 (D62)"
    assert not ({"acquired_at", "disposal_date"} <= facts.keys()) or (
        "months_since_acquisition" in facts
    ), "원천 2개가 있는데 파생이 없으면 트리거가 조용히 CLEAR 를 낸다"
    return facts


# ---------------------------------------------------------------- 판정

_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "is_null": lambda a, b: a is None,
    "is_not_null": lambda a, b: a is not None,
}


def _eval_cond(cond: dict, facts: dict) -> bool:
    op = _OPS[cond["op"]]
    return bool(op(facts.get(cond["field"]), cond.get("value")))


def _eval_trigger(trigger: dict, facts: dict) -> bool:
    if "all_of" in trigger:
        return all(_eval_cond(c, facts) for c in trigger["all_of"])
    if "any_of" in trigger:
        return any(_eval_cond(c, facts) for c in trigger["any_of"])
    raise ValueError("trigger는 all_of 또는 any_of를 가져야 한다")


@dataclass
class Finding:
    rule_id: str
    label: str
    verdict: str  # TRIGGERED | HOLD | CLEAR | INSUFFICIENT_FACTS
    disposal_type: str
    citations: list[str]
    law_refs: list[str]
    message: str
    resolve_options: list[str]
    reasoning: str
    requires_expert_review: bool
    rule_version: int
    missing_facts: list[str] = field(default_factory=list)


def evaluate_rule(rule: Rule, facts: dict, laws: dict[str, LawRef]) -> Finding:
    citations = [laws[r].citation() for r in rule.law_refs] + list(rule.contract_refs)

    def build(verdict: str, reasoning: str, missing: list[str] | None = None) -> Finding:
        return Finding(
            rule_id=rule.rule_id,
            label=rule.label,
            verdict=verdict,
            disposal_type=rule.disposal_type,
            citations=citations,
            law_refs=rule.law_refs,
            message=rule.message,
            resolve_options=rule.resolve_options,
            reasoning=reasoning,
            requires_expert_review=rule.requires_expert_review,
            rule_version=rule.rule_version,
            missing_facts=missing or [],
        )

    # ★ 이 검사는 **값이 아니라 키 존재**를 본다. `{"tax_credit_applied": None}` 은 여기서
    #   누락으로 잡히지 않는다 — NULL 을 "모른다"로 만드는 책임은 `build_facts` 가 키를
    #   **빼 주는** 데 있다. 엔진에서 `None` 을 누락 취급하면 "값이 없음이 확정된 사실"
    #   (담보 없는 자산의 `lien_creditor=''` 같은)과 구분이 불가능해진다.
    missing = [f for f in rule.required_facts if f not in facts]
    if missing:
        return build("INSUFFICIENT_FACTS", f"필수 사실 누락: {', '.join(missing)}", missing)

    # 경계 구간은 단정하지 않는다 (D62)
    if rule.boundary:
        value = facts.get(rule.boundary["field"])
        lo, hi = rule.boundary["review_band"]
        if value is not None and lo <= value <= hi:
            return build(
                rule.boundary.get("on_boundary", "HOLD"),
                f"{rule.boundary['field']}={value} 이(가) 경계 구간 [{lo}, {hi}] 내 → 사람 검토 필요. "
                + rule.boundary.get("note", ""),
            )

    triggered = _eval_trigger(rule.trigger, facts)
    used = {
        c["field"]: facts.get(c["field"])
        for c in rule.trigger.get("all_of", rule.trigger.get("any_of", []))
    }
    detail = ", ".join(f"{k}={v}" for k, v in used.items())
    return build("TRIGGERED" if triggered else "CLEAR", f"조건 평가: {detail}")


# 최상위 판정 어휘 5종 (D79). 우선순위 = 이 순서.
# `HOLD` 와 `INSUFFICIENT_FACTS` 를 합치지 않는 이유: **해소 경로가 정반대**다 —
#   HOLD = 경계 구간이라 *전문가 검토*가 필요 / INSUFFICIENT_FACTS = 사실이 없어 *데이터 입력*이 필요.
#   HTTP 는 셋 다 409 지만(D71) 사용자가 할 행동이 다르므로 본문 verdict 는 구분해야 한다.
# `holds` 를 `insufficient` 보다 앞에 두는 이유: 경계에 걸렸다는 건 룰이 **실제로 발동한**
#   양성 신호이고, 사실 누락은 판정 자체가 성립하지 않은 상태다 — 발화한 쪽이 더 구체적이다.
VERDICTS = ("BLOCKED", "HOLD", "INSUFFICIENT_FACTS", "CONDITIONAL", "CLEAR")

# 판정이 **보지 않은 축**. 여기 있는 문장은 엔진이 단일 출처다 (D73) —
# REST·도구가 문자열로 복제하면 엔진이 고칠 때 그쪽만 조용히 옛 문구를 낸다.
# 출력에는 `list(NOT_CONSIDERED)` 로 **새 리스트**를 실어 호출자가 상수를 변형하지 못하게 한다.
NOT_CONSIDERED: tuple[str, ...] = (
    "생산 계획·대체 설비 확보 여부",
    "시장 상황 및 매각 타이밍",
    "개별 계약의 특약 조항",
)

DISCLAIMER = "본 판정은 통상 사례 기준 목업 룰에 근거한다. 실제 적용에는 전문가 검토가 필요하다."


def laws_all_fetched(laws: dict[str, LawRef]) -> bool:
    """계층 1 전 건의 조문 **원문**이 수집됐는가.

    ★ 빈 dict 는 `False` 다. 0건에 `True` 를 주면 "전부 수집됐다"와 "아무것도 안 실렸다"가
      같은 값이 되고, 그 순간 소비자는 근거 없이 서명 경로를 연다 (D50 이 `error_codes`
      0행에서 막으려던 것과 같은 형태).
    """
    return bool(laws) and all(law.is_fetched for law in laws.values())


def assert_rules_resolvable(rules: dict[str, Rule], laws: dict[str, LawRef]) -> None:
    """주입된 카탈로그에도 로더와 **같은 불변식**을 적용한다 (D61 불변식 2).

    주입 경로라고 게이트를 낮추면, 파일·DB 로더가 지키는 "근거 없는 룰은 존재할 수 없다"가
    세 번째 입구로 우회된다. 미등록 참조는 `evaluate_rule` 의 `laws[r]` 에서 KeyError 로
    터지기도 하지만, 그건 판정 시점이라 D61 이 정한 "로드 단계에서 막는다"보다 훨씬 뒤다.
    """
    for rule in rules.values():
        if not rule.law_refs and not rule.contract_refs:
            raise RuleIntegrityError(f"{rule.rule_id}: 근거 참조 없음")
        for ref in rule.law_refs:
            if ref not in laws:
                raise RuleIntegrityError(f"{rule.rule_id}: 미등록 법령 참조 {ref}")


def check_disposal_blockers(
    facts: dict,
    at: date | None = None,
    *,
    laws: dict[str, LawRef] | None = None,
    rules: dict[str, Rule] | None = None,
) -> dict:
    """S9의 진입점. BLOCKING / PRECONDITION / HOLD / INSUFFICIENT_FACTS 를 분리해 반환한다.

    **주입점 (D82).** `laws`/`rules` 가 `None` 이면 현행대로 파일 로더를 쓴다 —
    기존 호출자 3곳(MCP 도구·REST 서비스·`test_rules`)은 한 줄도 바뀌지 않는다.
    주입되면 `load_laws()`/`load_rules()` 를 **호출하지 않는다**: 소비자가
    "판정이 본 조문"과 "해시로 고정한 조문"을 **같은 객체**로 만들 수 있어야 하기 때문이다
    (W5 — 지금은 인용이 파일 사본, `text_hash` 가 DB 사본에서 와 서로 다른 사본이다).

    반환 dict 의 `facts_used`·`laws_used` 는 **소비자가 판정 입력을 재조립하지 않게** 하려는
    것이다. 재조립하면 같은 이원화가 `facts` 축에서 그대로 반복된다.
    """
    at = at or date.today()
    if laws is None:
        laws = load_laws()
    if rules is None:
        rules = load_rules(laws)  # 주입된 laws 로 로드 — 무결성 게이트가 같은 사본을 본다
    else:
        assert_rules_resolvable(rules, laws)

    findings = [evaluate_rule(r, facts, laws) for r in rules.values()]

    blockers = [f for f in findings if f.verdict == "TRIGGERED" and f.disposal_type == "BLOCKING"]
    preconds = [
        f for f in findings if f.verdict == "TRIGGERED" and f.disposal_type == "PRECONDITION"
    ]
    holds = [f for f in findings if f.verdict == "HOLD"]
    insufficient = [f for f in findings if f.verdict == "INSUFFICIENT_FACTS"]

    if blockers:
        verdict = "BLOCKED"
    elif holds:
        verdict = "HOLD"
    elif insufficient:
        verdict = "INSUFFICIENT_FACTS"  # D79 — 'HOLD' 에 흡수하지 않는다
    elif preconds:
        verdict = "CONDITIONAL"
    else:
        verdict = "CLEAR"

    return {
        # 처분 판정의 대상은 인버터가 아니라 **호스트 설비**다 (D68)
        "asset_id": facts.get("asset_id"),
        "evaluated_at": at.isoformat(),
        "verdict": verdict,
        "blockers": [f.__dict__ for f in blockers],
        "preconditions": [f.__dict__ for f in preconds],
        "holds": [f.__dict__ for f in holds],
        "insufficient": [f.__dict__ for f in insufficient],
        # ── D82 — 판정이 실제로 무엇을 보았는가
        # `facts_used` 는 입력의 **얕은 사본**이다. 필터·재조립하지 않는다: 걸러 내면
        # "판정이 본 사실"과 "번들에 실린 사실"이 또 갈린다. 사본인 이유는 호출자가
        # 변형해도 엔진에 되돌아오지 않게 하기 위함이며, 중첩 값은 공유된다 —
        # `build_facts` 가 스칼라만 만들기 때문에 실무상 문제가 되지 않는다.
        "facts_used": dict(facts),
        # 인용 여부와 무관하게 **평가된 전 룰**의 참조를 싣는다. 발화한 룰만 세면
        # 전 룰 CLEAR 인 자산에서 빈 목록이 되어 "근거를 조회한 결과 해당 없음"과
        # "근거를 아예 안 봤다"가 구분되지 않는다 (W7).
        "laws_used": sorted({ref for r in rules.values() for ref in r.law_refs}),
        "not_considered": list(NOT_CONSIDERED),
        "disclaimer": DISCLAIMER,
    }
