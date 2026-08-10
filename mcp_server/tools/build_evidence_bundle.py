# -*- coding: utf-8 -*-
"""build_evidence_bundle — 처분 판정의 근거를 계층 1+2+사실로 묶고 해시로 고정한다 (S10 계층 3의 재료).

이 도구가 만드는 것은 **판정이 아니라 판정의 증빙**이다. 판정 로직(verdict 5종·우선순위·버킷)은
`data.rules.engine` 안에만 있고 여기서는 **그 엔진을 직접 호출해** 결과와 근거를 그대로 싣는다.
Sprint 7 의 사람 전용 서명 API 가 이 번들과 해시를 `decisions` 에 저장한다.

────────────────────────────────────────────────────────────────────────────────
★ 왜 MCP 도구(`check_disposal_blockers`)를 경유하지 않는가 — W5 (D82)
────────────────────────────────────────────────────────────────────────────────
Sprint 6 까지 이 파일은 `check_disposal_blockers` **도구**를 부른 뒤 조문을 **다시** 읽고
사실을 **다시** 조립했다. 그 결과 인용 집합은 *파일 사본* 판정에서, `text_hash`·
`effective_from` 은 *DB 사본* 에서 왔다 — 즉 **"판정이 본 조문"과 "해시로 고정한 조문"이
서로 다른 사본**이었다. 서명 산출물에서 이건 치명적이다: 해시는 판정이 보지 않은 문서를
가리키게 된다.

지금은 **원천을 하나로 묶는다.**

    with read_only() as con:
        laws  = engine.load_laws_from_db(con)          # ← 계층 1 사본을 한 번만 읽고
        rules = engine.load_rules_from_db(con, laws)   # ← 계층 2도 같은 사본에서
        judgment = engine.check_disposal_blockers(facts, laws=laws, rules=rules)   # 주입

  - 판정·인용·`text_hash`·`effective_from`·`rule_hash` 가 **전부 같은 객체**에서 나온다.
  - `facts` 는 엔진이 돌려준 `facts_used` 를 **그대로** 싣는다. 재조립하면 같은 이원화가
    `facts` 축에서 반복된다(엔진이 본 값과 번들에 실린 값이 갈린다).
  - ⛔ 한 호출 안에서 파일 로더(`load_laws`)와 DB 로더(`load_laws_from_db`)를 **섞지 말 것.**
  - MCP 도구 경유가 불가능한 실무적 이유도 있다: 그 도구의 출력은 `04 §8` 13키로
    화이트리스트 고정돼 있어 `facts_used`·`laws_used` 가 **애초에 나오지 않는다.**

  두 사본이 어긋나면(파일 정본 ≠ DB 사본) 판정도 갈릴 수 있다 — 그건 `data/seed.py` ⑬⑭ 와
  `spikes/rules_db_load.py` 가 먼저 잡는다. 이 도구는 **한 사본만** 본다.

────────────────────────────────────────────────────────────────────────────────
★ 번들 5키 (D83) — 무엇을 왜 싣는가
────────────────────────────────────────────────────────────────────────────────
  `laws[]`      4버킷에 실린 findings 의 `law_refs` **합집합만**. `text_hash` 필수 →
                미수집이면 `law_text_unavailable` (아래).
  `rules[]`     인용된 룰 + **`rule_hash`** (W6). 계층 1은 `text_hash` 로 잠겨 있는데
                계층 2는 `rule_version` 숫자로만 잠겨 있었다 — 같은 버전 안에서 룰 본문이
                in-place 로 바뀌어도 번들 해시가 그대로였다.
  `evaluated[]` **평가된 전 룰**의 `{rule_id, rule_version, verdict, law_refs}` (W7).
                CLEAR 자산은 `laws`·`rules` 가 비므로, 이게 없으면 *"근거를 조회한 결과
                해당 없음"* 과 *"근거를 아예 안 봤다"* 가 번들에서 구분되지 않는다.
                ⛔ 여기엔 `text_hash` 를 **요구하지 않는다.** 평가만 하고 발화하지 않은 룰의
                조문 원문까지 해시로 요구하면 **미수집 조문 1건이 전 자산의 서명 경로를
                잠근다** — W7 이 해소하려던 건 "무엇을 평가했는가"이지 그게 아니다.
  `contracts[]` 인용된 룰의 `contract_refs`. `text_hash: null` · `hash_fixed: false`.
                ⛔ **`law_text_unavailable` 검사 대상이 아니다.** 계약 조항은 법제처 수집
                대상이 아니므로 검사에 넣으면 `LIEN-CONSENT` 가 걸린 자산의 번들이
                구조적으로 영원히 불가능해진다 (`04 §14` 명시).
  `facts`       엔진이 돌려준 `facts_used` **그대로** (D62 — NULL 컬럼은 키 자체가 없다).

────────────────────────────────────────────────────────────────────────────────
★ `bundle_hash` 산출 규약 (Sprint 7 의 서명 검증이 **같은 함수를 그대로 써야 한다**)
────────────────────────────────────────────────────────────────────────────────
    canonical_json(obj) = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"))
    bundle_hash         = engine.text_hash(canonical_json(bundle))   # "sha256:…"

  네 가지를 **전부** 고정해야 "같은 사실 → 같은 해시"가 성립한다:

  1. `sort_keys=True` — dict 는 삽입 순서를 보존하므로, 고정하지 않으면 `facts` 를 만든
     순서만 달라도 다른 해시가 난다. 서명 검증이 "근거가 바뀌었다"고 오탐하게 된다.
  2. `separators=(",", ":")` — 기본 구분자는 `", "`·`": "` 라 공백이 들어간다.
     `engine.normalize()` 는 공백을 **지우는 게 아니라 하나로 접는다** — 즉 구분자 차이는
     정규화로 흡수되지 **않는다.** 그래서 이건 선택이 아니라 필수 규약이다.
  3. `ensure_ascii=False` — 한글을 `\\uXXXX` 로 이스케이프하면 같은 문자열이 두 표현을
     갖는다. NFKC 는 이스케이프 시퀀스를 되돌리지 못한다.
  4. `engine.text_hash()` 재구현 금지 — 이 함수가 NFKC + 공백 정규화를 적용한다.
     계층 1 조문 해시와 **같은 규칙**이어야 이원화가 생기지 않는다.

  ⚠ N1 — **해시 동일 ≠ 바이트 동일.** 기준은 *NFKC + 공백 정규화 후 동일* 이다.
    그 사실을 `hash_spec` 필드와 `disclaimer` 로 밖에 드러낸다. `hash_spec` 은 번들
    **밖**이다 — 안에 넣으면 스펙 문자열을 한 글자 고치는 순간 과거 서명이 전부 깨진다.
  ⚠ `built_at`·`evaluated_at` 도 번들 **밖**이다. 안에 넣으면 같은 사실도 호출할 때마다
    해시가 달라져 "근거가 변조되지 않았음"을 증명할 수 없다.
  ⚠ 리스트 4종은 **순서가 해시에 영향을 준다.** `sort_keys` 는 리스트를 정렬해 주지 않으므로
    조립 시점에 명시적으로 정렬한다 — `laws`→`law_ref_id`, `rules`·`evaluated`→
    `(rule_id, rule_version)`, `contracts`→`contract_ref`.

────────────────────────────────────────────────────────────────────────────────
★ 미수집 조문이 하나라도 있으면 **의도적으로 거부**한다 (`law_text_unavailable`)
────────────────────────────────────────────────────────────────────────────────
MQ-701(Sprint 7)에서 법제처 OPEN API 로 조문을 실수집해 **7건 중 6건이 `FETCHED`** 가 됐고,
처분 룰이 인용하는 조문은 그 6건에 전부 포함되므로 **실 DB 에서 이 도구는 성공한다.**
남은 1건(`KR-CITA-ENF-31`)은 제목이 API 값과 달라 사람 승인 대기이며 어떤 룰도 인용하지 않는다.
**이 거부 경로를 지우지 말 것** — 새 룰이 미수집 조문을 인용하면 즉시 다시 필요하다.

`text_hash` 가 null 인 항목을 조용히 넣고 해시하면 **해시할 사실이 없는 번들**이 나온다.
번들의 존재 이유는 "이 결정이 참조한 근거가 이후 변조되지 않았음"의 증명인데, 근거 원문이
없으면 그 증명은 빈 약속이다 (`11 §2`). D50·D62 가 반복해서 막아 온 유형의 계층 1 판이다.

  판정 자체는 조문 원문 없이도 성립한다. **막는 것은 판정이 아니라 서명용 증빙 생성뿐**이다.

────────────────────────────────────────────────────────────────────────────────
그 밖에 지켜야 할 것
────────────────────────────────────────────────────────────────────────────────
  - ⛔ **아무것도 저장하지 않는다 (D10).** `decisions` INSERT 는 사람 전용 API 가 한다.
    여기엔 쓰기 커넥션조차 없다 — `read_only()` 만 쓴다.
  - ⛔ **verdict 5종·우선순위·버킷 분류를 재계산하지 않는다.** 그건 엔진 안에만 있다.
    `evaluated[]` 의 룰별 verdict 도 **엔진의 같은 함수**(`engine.evaluate_rule`)로 얻고,
    4버킷과 **교차 검증**한다(어긋나면 `engine_error`). 버킷에 없는 룰을 CLEAR 로
    *추정하지 않는* 이유: `AUTO_CLOSE` 룰이 TRIGGERED 여도 4버킷 어디에도 담기지 않으므로,
    추정하면 발화한 룰이 번들에 "CLEAR"로 기록된다 (D62 — 모른다를 통과로 반올림 금지).
  - **N2 — 판정 전과 번들 조립 후 자산 행을 두 번 읽는다.** 사이에 행이 바뀌면
    `asset_modified`, 사라지면 `asset_disappeared`. 번들은 "그 시점의 사실"에 대한 서명
    재료이므로, 조립 도중 사실이 움직였다면 그 번들은 어느 시점도 증명하지 못한다.
  - **`disposal_mode` 는 `engine.DISPOSAL_MODES` 를 단일 출처로 검증**한다. 폴백 금지 —
    'SELL' 을 'SALE' 로 고쳐 주면 오타 하나가 `VAT-INVOICE` 트리거를 빗나가 판정을 바꾼다.
  - **예외를 던지지 않는다 (D9·D46).**

`mcp_server` 는 `backend` 를 import 하지 않는다(D15). `data.rules.engine` 은 데이터 계층이라
허용된다(D73) — `server.py:28` 이 레포 루트를 `sys.path` 에 넣는다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from data.rules import engine

from ..db import read_only

# 자산 참조 규약(`asset_id | equipment_id` 해석·처분 인자 검증)은 `04 §8`·`§14` 공용이라
# `_asset_ref` 에 한 벌만 둔다. **판정 도구를 경유하는 것이 아니다** — `_asset_ref` 는
# 두 도구 어느 쪽도 import 하지 않으므로 W5(원천 이원화)·DoD ⑰ 에 걸리지 않는다.
# 그 사실은 `spikes/bundle_integrity.py` 가 정적(import 라인)·런타임(자식 sys.modules)
# 양쪽으로 검사한다.
from ._asset_ref import err as _err, parse_disposal_args, resolve_asset_id

DESCRIPTION = (
    "처분 판정의 근거(법령 조문·해석 룰·판정에 쓰인 사실)를 하나로 묶고 해시로 고정한다. "
    "매각·폐기 결정을 문서로 남기거나 결재·서명에 올릴 때 호출할 것. "
    "asset_id 또는 equipment_id **둘 중 하나는 반드시 넘겨야 한다** (둘 다 비우면 실패한다). "
    "처분 예정일을 알면 disposal_date 를 함께 넘길 것 — 없으면 세액공제 조항이 사실 부족으로 남는다. "
    "이 도구는 판정하지도 저장하지도 않는다. 판정은 check_disposal_blockers 가 하고, "
    "번들의 저장·서명은 사람이 승인 화면에서 한다. "
    "law_text_unavailable 로 실패하면 조문 원문이 아직 수집되지 않았다는 뜻이며, "
    "'근거가 없다'가 아니라 '근거 원문을 아직 해시할 수 없다'는 뜻이다 — 판정 결과는 "
    "check_disposal_blockers 로 그대로 얻을 수 있다."
)

# 엔진이 돌려주는 판정 버킷 4종. 이 넷에 등장한 룰이 곧 "이 판정이 인용한 룰"이다.
# CLEAR 자산은 넷이 전부 비어 `rules`·`laws` 가 빈 배열이 된다 — **빈 근거도 사실이므로**
# 해시는 그대로 산출하고, 무엇을 평가했는지는 `evaluated[]` 가 말한다 (W7).
_BUCKETS = ("blockers", "preconditions", "holds", "insufficient")

# 엔진 반환 중 이 도구가 **반드시 있어야 하는** 키. 없으면 부분 응답을 정상으로 포장하지 않는다.
# `facts_used`·`laws_used` 는 D82 의 산출물이며, 이 둘이 없으면 W5 를 해소할 수 없다.
_REQUIRED_JUDGMENT_KEYS = ("verdict", "facts_used", "laws_used", "not_considered", *_BUCKETS)

# 해시 규약의 이름. **번들 밖**에 싣는다 (N1) — 안에 넣으면 이 문자열을 고치는 순간
# 과거 서명의 해시가 전부 달라진다. 값의 뜻: sha256 / NFKC+공백정규화 / canonical-json v1.
HASH_SPEC = "sha256/nfkc-ws/canonical-json-v1"

# ── W6 — `rule_hash` 대상 필드 ────────────────────────────────────────────────
# `engine.Rule` 의 **판정에 영향을 주는 전 필드**다. 하나라도 바뀌면 같은 `rule_version`
# 이어도 해시가 달라져야 한다("계층 2가 버전 번호로만 잠겨 있다"는 W6 의 지적).
#
# ⛔ `authored_by`·`reviewed_at`·`revision_note` 는 **제외**한다. 셋 다 룰 JSON 에는 있지만
#    판정 입력이 아닌 **메타데이터**라, 넣으면 "검토자 이름 오타 수정"이나 "개정 사유 문구
#    다듬기"가 서명 검증에서 **근거 변조**로 보고된다. 실제로 셋은 `engine.Rule` dataclass
#    에도 실리지 않으므로(엔진이 판정에 쓰지 않는다는 뜻) 이 제외는 구조와도 일치한다.
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

_DISCLAIMER = (
    "이 번들은 판정 시점의 근거 스냅샷이며 판정 자체가 아니다. bundle_hash 는 evidence_bundle "
    "다섯 항목(laws·rules·evaluated·contracts·facts)만을 대상으로 하며 built_at·hash_spec 은 "
    "포함하지 않는다(같은 사실은 언제 조립해도 같은 해시). "
    "변조 없음의 기준은 바이트 동일이 아니라 NFKC + 공백 정규화 후 동일이다 — 전각/반각·"
    "연속 공백 차이는 같은 근거로 본다(hash_spec 참조). "
    "contracts 항목은 원문 원천이 저장소에 없어 해시로 고정되지 않는다(hash_fixed=false). "
    "처분 확정은 사람의 서명으로만 이뤄지고, 시스템 판정과 다른 결정은 사유 기재와 함께 기록된다."
)


def canonical_json(obj: Any) -> str:
    """정준 직렬화. **해시를 내는 모든 곳이 이 함수 하나만 쓴다.**

    Sprint 7 의 서명 검증(`decisions.bundle_hash` 재계산)도 이 함수를 import 해서 쓸 것.
    직렬화 규약을 각자 재현하면 같은 번들에 두 해시가 생겨 검증이 무의미해진다.
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_bundle_hash(bundle: dict) -> str:
    """`canonical_json` → `engine.text_hash`. 해시 함수를 재구현하지 않는다 (계층 1과 동일 규칙)."""
    return engine.text_hash(canonical_json(bundle))


def rule_hash(rule: engine.Rule) -> str:
    """룰 **본문**의 해시 (W6). 메타 3필드 제외 근거는 `RULE_HASH_FIELDS` 주석 참조."""
    return engine.text_hash(canonical_json({k: getattr(rule, k) for k in RULE_HASH_FIELDS}))


def _facts_fingerprint(facts: dict) -> str:
    """자산 사실의 지문 (N2). `bundle_hash` 와 **같은 규약**으로 낸다 — 두 벌의 정규화 규칙이
    생기면 "사실이 바뀌었다"의 기준이 도구 안에서 둘로 갈린다."""
    return engine.text_hash(canonical_json(facts))


def _law_entry(law: engine.LawRef) -> dict:
    """번들에 싣는 조문 항목. **원문 전체는 싣지 않고 해시로만 고정한다.**

    원문을 그대로 넣으면 번들이 수 KB 로 부풀고, 그럼에도 무결성 보장은 해시와 동일하다.
    `effective_from` 을 함께 싣는 이유: 같은 조문 번호라도 시행일이 다르면 다른 사실이다.
    """
    return {
        "law_ref_id": law.law_ref_id,
        "effective_from": law.effective_from,
        "text_hash": law.text_hash,
    }


def _is_hashable_evidence(law: engine.LawRef | None) -> bool:
    """해시할 사실이 실제로 있는가.

    `fetch_status == 'FETCHED'` 만 보면 **본문 없는 행이 완전한 근거로 계산된다.**
    `is_fetched` 는 상태와 원문을 함께 보고, 여기에 `text_hash` 존재까지 더한다 —
    번들이 싣는 값이 바로 그 해시이므로, 해시가 없으면 실을 것이 없다.
    """
    return law is not None and law.is_fetched and bool(law.text_hash)


def _cited_rule_keys(judgment: dict) -> list[tuple[str, Any]]:
    """4버킷에 등장한 룰의 `(rule_id, rule_version)` 유일키 (정렬).

    유일키에 `rule_version` 을 포함하는 이유: 같은 룰의 개정본이 공존할 수 있고(D60),
    **서명은 그때 그 버전에 대해 이뤄진 것**이기 때문이다.
    """
    seen: set[tuple[str, Any]] = set()
    for bucket in _BUCKETS:
        for item in judgment.get(bucket) or []:
            rule_id = item.get("rule_id")
            if rule_id is not None:
                seen.add((rule_id, item.get("rule_version")))
    return sorted(seen, key=lambda k: (str(k[0]), str(k[1])))


def _bucket_verdicts(judgment: dict) -> dict[tuple[str, Any], str]:
    """`(rule_id, rule_version)` → 버킷이 기록한 룰별 verdict. `evaluated[]` 교차 검증용."""
    out: dict[tuple[str, Any], str] = {}
    for bucket in _BUCKETS:
        for item in judgment.get(bucket) or []:
            rule_id = item.get("rule_id")
            if rule_id is not None:
                out[(rule_id, item.get("rule_version"))] = item.get("verdict")
    return out


def _cited_law_ref_ids(judgment: dict) -> list[str]:
    """인용된 룰들의 `law_refs` **합집합**(정렬). 계약 근거(`contract_refs`)는 조문이 아니다.

    조문 원문이 없는 계약 근거까지 여기서 요구하면 `여신거래기본약관`(CONTRACT 근거)이
    영원히 `law_text_unavailable` 을 만든다 — 애초에 법제처 수집 대상이 아니다.
    계약 근거는 `contracts[]` 에 `hash_fixed:false` 로 따로 실린다.
    """
    refs: set[str] = set()
    for bucket in _BUCKETS:
        for item in judgment.get(bucket) or []:
            for ref in item.get("law_refs") or []:
                refs.add(ref)
    return sorted(refs)


def _evaluated_entries(
    rules: dict[str, engine.Rule], facts: dict, laws: dict[str, engine.LawRef]
) -> list[dict]:
    """W7 — **평가된 전 룰**의 `{rule_id, rule_version, verdict, law_refs}` (정렬).

    룰별 verdict 는 엔진의 `evaluate_rule` 로 얻는다. 판정 우선순위(D79)를 다시 계산하는
    것이 아니라 **엔진이 이미 쓴 순수 함수를 같은 입력으로 부르는 것**이며, 결과는 아래에서
    4버킷과 교차 검증된다. 버킷에 없는 룰을 CLEAR 로 추정하지 않는 이유는 모듈 docstring 참조.

    ⛔ 항목에 `text_hash` 를 넣지 않는다 (D83) — 평가만 하고 발화하지 않은 룰의 조문까지
      원문을 요구하면 미수집 1건이 전 자산의 서명 경로를 잠근다.
    """
    entries = [
        {
            "rule_id": rule.rule_id,
            "rule_version": rule.rule_version,
            "verdict": engine.evaluate_rule(rule, facts, laws).verdict,
            "law_refs": list(rule.law_refs or []),
        }
        for rule in rules.values()
    ]
    return sorted(entries, key=lambda e: (str(e["rule_id"]), str(e["rule_version"])))


def _build(
    asset_id: str | None,
    equipment_id: str | None,
    disposal_mode: str,
    disposal_date: str | None,
) -> dict:
    # 읽기 전용 커넥션만 쓴다 (D10). 판정·해시·재읽기가 **같은 커넥션·같은 사본**을 본다.
    with read_only() as con:
        # ── ① 계층 1·2 사본을 **한 번만** 읽는다 (W5 원천 일원화)
        laws = engine.load_laws_from_db(con)
        if not laws:
            # 0행을 "조건 없음"으로 주면 모든 자산이 CLEAR 로 통과한다 (D50).
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

        # ── ② 판정 **전** 자산 행 (N2 의 첫 번째 읽기)
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

        # ── ③ 판정. **엔진에 laws·rules 를 주입**한다 (W5) — MCP 도구를 경유하지 않는다.
        judgment = engine.check_disposal_blockers(facts, laws=laws, rules=rules)

        absent = [k for k in _REQUIRED_JUDGMENT_KEYS if k not in judgment]
        if absent:
            return _err(
                "engine_error",
                f"룰 엔진 반환에 필요한 키가 없습니다: {', '.join(absent)} "
                "(facts_used·laws_used 는 D82 의 주입점 산출물입니다)",
            )
        verdict = judgment["verdict"]
        if verdict not in engine.VERDICTS:
            # 엔진이 계약 밖 어휘를 냈다. 모르는 판정을 통과로 포장하지 않는다.
            return _err("engine_error", f"룰 엔진이 계약 밖 verdict 를 반환했습니다: {verdict!r}")

        # ★ 판정이 실제로 본 사실을 **그대로** 싣는다. 재조립 금지 (W5 의 facts 축).
        facts_used = judgment["facts_used"]

        # ── ④ 인용 근거 조립. 전부 위에서 읽은 **같은 객체**에서 꺼낸다.
        cited_keys = _cited_rule_keys(judgment)
        cited_law_ids = _cited_law_ref_ids(judgment)

        rule_entries: list[dict] = []
        contract_refs: set[str] = set()
        for rule_id, rule_version in cited_keys:
            rule = rules.get(rule_id)
            if rule is None or rule.rule_version != rule_version:
                # 판정이 인용한 룰을 카탈로그에서 되짚지 못하면 `rule_hash` 를 낼 수 없다.
                # 해시 없는 룰 항목을 조용히 싣지 않는다 — 그게 W6 가 막으려던 상태다.
                return _err(
                    "engine_error",
                    f"판정이 인용한 룰을 카탈로그에서 찾지 못했습니다: {rule_id} v{rule_version}",
                )
            rule_entries.append(
                {
                    "rule_id": rule.rule_id,
                    "rule_version": rule.rule_version,
                    "rule_hash": rule_hash(rule),
                }
            )
            contract_refs.update(rule.contract_refs or [])

        # ── ⑤ 조문 원문 게이트. **계약 근거는 대상이 아니다** (`04 §14`).
        missing = [rid for rid in cited_law_ids if not _is_hashable_evidence(laws.get(rid))]
        if missing:
            return _err(
                "law_text_unavailable",
                "인용 조문의 원문이 아직 수집되지 않아 근거 번들을 만들 수 없습니다 "
                f"(미수집 {len(missing)}건: {', '.join(missing)}). "
                "text_hash 가 없는 항목을 넣으면 해시할 사실이 없어 번들이 무결성을 "
                "증명하지 못합니다. 판정 결과 자체는 check_disposal_blockers 로 확인하세요.",
                asset_id=resolved_id,
                missing_law_refs=missing,
            )

        # ── ⑥ W7 — 평가된 전 룰. 4버킷과 교차 검증한다.
        evaluated = _evaluated_entries(rules, facts_used, laws)
        by_key = {(e["rule_id"], e["rule_version"]): e["verdict"] for e in evaluated}
        drift = [
            f"{rid} v{ver}: 버킷={bucket_verdict} vs 재평가={by_key.get((rid, ver))}"
            for (rid, ver), bucket_verdict in _bucket_verdicts(judgment).items()
            if by_key.get((rid, ver)) != bucket_verdict
        ]
        if drift:
            return _err("engine_error", "판정 버킷과 룰별 재평가가 어긋납니다: " + "; ".join(drift))

        # `laws_used`(D82) 를 **소비**한다 — 엔진이 본 조문 집합과 evaluated 의 합집합이
        # 어긋나면 둘 중 하나가 카탈로그를 다르게 본 것이다.
        union = sorted({ref for e in evaluated for ref in e["law_refs"]})
        if union != list(judgment["laws_used"]):
            return _err(
                "engine_error",
                f"laws_used({judgment['laws_used']}) 와 evaluated 의 조문 합집합({union}) 이 "
                "일치하지 않습니다",
            )

        # ── ⑦ 번들 조립. 리스트 4종은 **명시적으로 정렬**한다.
        bundle = {
            "laws": [_law_entry(laws[rid]) for rid in cited_law_ids],  # law_ref_id 정렬
            "rules": rule_entries,  # (rule_id, rule_version) 정렬
            "evaluated": evaluated,  # (rule_id, rule_version) 정렬
            "contracts": [
                {
                    "contract_ref": ref,
                    "text_hash": None,
                    "hash_fixed": False,
                    "note": _CONTRACT_NOTE,
                }
                for ref in sorted(contract_refs)  # contract_ref 정렬
            ],
            "facts": facts_used,
        }

        # ── ⑧ N2 — 번들 조립 **후** 자산 행을 다시 읽는다.
        after = con.execute("SELECT * FROM assets WHERE asset_id = ?", (resolved_id,)).fetchone()
        if after is None:
            # 판정 직후에 자산이 사라진 경우(외부 재시드 등). 사실 없이 번들을 만들지 않는다.
            return _err(
                "asset_disappeared",
                f"판정 직후 자산 행을 다시 읽지 못했습니다: {resolved_id}",
                asset_id=resolved_id,
            )
        after_facts = engine.build_facts(
            after, disposal_mode=disposal_mode, disposal_date=disposal_date
        )
        if _facts_fingerprint(after_facts) != _facts_fingerprint(facts_used):
            # 조립 도중 사실이 움직였다. 이 번들은 어느 시점의 사실도 증명하지 못한다 —
            # 조용히 이전 스냅샷으로 해시를 내면 서명이 "이미 지난 사실"에 걸린다.
            return _err(
                "asset_modified",
                f"판정 직후 자산 행이 변경됐습니다: {resolved_id} — 근거 번들은 한 시점의 "
                "사실에 대한 서명 재료이므로, 조립 도중 사실이 바뀌면 만들지 않습니다. "
                "다시 호출하세요.",
                asset_id=resolved_id,
            )

    return {
        "status": "ok",
        "asset_id": resolved_id,
        "evidence_bundle": bundle,
        "bundle_hash": compute_bundle_hash(bundle),
        # 해시 규약의 이름. **번들 밖**이다 (N1) — 안에 넣으면 스펙 문자열 변경이 해시를 흔든다.
        "hash_spec": HASH_SPEC,
        "verdict": verdict,
        # 불변식 6 — `verdict` 를 최상위에 싣는 순간 소비자에게 이 응답은 **판정 결과로 읽힌다.**
        # 그러면 "무엇을 고려하지 않았는가"가 따라와야 한다.
        # ⛔ 문장을 새로 만들지 않는다. 판정 주체(엔진)가 정한 목록을 **그대로** 옮긴다.
        # ⛔ 번들 **밖**이다. 안에 넣으면 목록 문구가 바뀔 때 `bundle_hash` 가 함께 흔들려
        #    "근거가 변조됐다"는 오탐이 난다.
        "not_considered": judgment["not_considered"],
        # 번들 **밖**이다. 안에 넣으면 같은 사실이 매 호출 다른 해시를 낸다.
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": _DISCLAIMER,
    }


def build_evidence_bundle(
    asset_id: str | None = None,
    equipment_id: str | None = None,
    disposal_mode: str = "SALE",
    disposal_date: str | None = None,
) -> dict:
    """처분 판정의 근거를 묶고 `bundle_hash` 로 고정한다. 저장은 하지 않는다 (D10).

    `asset_id`·`equipment_id` 는 **둘 중 하나 필수**라 시그니처상 둘 다 optional 이다
    (D80 의 either-or 공백). 스키마로는 막을 수 없으므로 `DESCRIPTION` 이 그 사실을 말하고,
    둘 다 비면 여기서 `invalid_input` 으로 되돌린다.

    실패는 예외가 아니라 `status` 로 돌려준다 (D9·D46).
    """
    try:
        # 입력 검증·폴백 금지 규약은 `_asset_ref` 한 곳에 있다 — `check_disposal_blockers` 와
        # **같은 reason·같은 문구**를 내야 하기 때문이다 (bundle_integrity 가 8케이스 대조).
        args, failure = parse_disposal_args(asset_id, equipment_id, disposal_mode, disposal_date)
        if args is None:
            # 배타적 반환 — `args` 가 없으면 `failure` 가 반드시 있다 (`resolve_asset_id` 와 같은 규약).
            return failure or _err("invalid_input", "처분 인자를 해석하지 못했습니다")
        return _build(args.asset_id, args.equipment_id, args.disposal_mode, args.disposal_date)

    except engine.RuleIntegrityError as e:
        # 근거 없는 룰이 카탈로그에 있다 (D61). 번들을 내면 근거 없는 서명 재료가 된다.
        return _err("rule_integrity", f"룰 카탈로그 무결성 위반: {e}")
    except FileNotFoundError as e:
        return _err("db_missing", str(e))
    except (sqlite3.Error, OSError) as e:
        return _err("db_error", str(e))
    except Exception as e:  # noqa: BLE001 — 엔진·직렬화 예외를 status 로 바꿔 반환한다 (D9)
        return _err("internal_error", f"{type(e).__name__}: {e}")
