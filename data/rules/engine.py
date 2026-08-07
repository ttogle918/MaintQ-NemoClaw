"""
룰 평가 엔진 — 계층 1(법령 스냅샷) · 계층 2(해석 룰) 사이의 결정론적 판정기.

설계 원칙:
  1. LLM은 이 엔진을 호출할 뿐, 판정을 직접 만들지 않는다.
  2. 근거(law_refs 또는 contract_refs)가 없는 룰은 로드 자체가 거부된다 (D61).
  3. 경계 구간(boundary.review_band)은 단정하지 않고 HOLD를 반환한다 (D62).
"""

from __future__ import annotations

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
    used = {c["field"]: facts.get(c["field"]) for c in rule.trigger.get("all_of", rule.trigger.get("any_of", []))}
    detail = ", ".join(f"{k}={v}" for k, v in used.items())
    return build("TRIGGERED" if triggered else "CLEAR", f"조건 평가: {detail}")


def check_disposal_blockers(facts: dict, at: date | None = None) -> dict:
    """S9의 진입점. BLOCKING / PRECONDITION / HOLD를 분리해 반환한다."""
    at = at or date.today()
    laws = load_laws()
    rules = load_rules(laws)

    findings = [evaluate_rule(r, facts, laws) for r in rules.values()]

    blockers = [f for f in findings if f.verdict == "TRIGGERED" and f.disposal_type == "BLOCKING"]
    preconds = [f for f in findings if f.verdict == "TRIGGERED" and f.disposal_type == "PRECONDITION"]
    holds = [f for f in findings if f.verdict == "HOLD"]
    insufficient = [f for f in findings if f.verdict == "INSUFFICIENT_FACTS"]

    if blockers:
        verdict = "BLOCKED"
    elif holds or insufficient:
        verdict = "HOLD"
    elif preconds:
        verdict = "CONDITIONAL"
    else:
        verdict = "CLEAR"

    return {
        "equipment_id": facts.get("equipment_id"),
        "evaluated_at": at.isoformat(),
        "verdict": verdict,
        "blockers": [f.__dict__ for f in blockers],
        "preconditions": [f.__dict__ for f in preconds],
        "holds": [f.__dict__ for f in holds],
        "insufficient": [f.__dict__ for f in insufficient],
        "not_considered": [
            "생산 계획·대체 설비 확보 여부",
            "시장 상황 및 매각 타이밍",
            "개별 계약의 특약 조항",
        ],
        "disclaimer": "본 판정은 통상 사례 기준 목업 룰에 근거한다. 실제 적용에는 전문가 검토가 필요하다.",
    }
