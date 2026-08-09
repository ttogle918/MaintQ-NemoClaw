# -*- coding: utf-8 -*-
"""build_evidence_bundle — 처분 판정의 근거를 계층 1+2+사실로 묶고 해시로 고정한다 (S10 계층 3의 재료).

이 도구가 만드는 것은 **판정이 아니라 판정의 증빙**이다. 판정은 `check_disposal_blockers` 가
하고(중복 구현 금지), 여기서는 그 판정이 **무엇을 근거로 삼았는지**를 조립해 해시를 낸다.
Sprint 7 의 사람 전용 서명 API 가 이 번들과 해시를 `decisions` 에 저장한다.

────────────────────────────────────────────────────────────────────────────────
★ `bundle_hash` 산출 규약 (Sprint 7 의 서명 검증이 **같은 함수를 그대로 써야 한다**)
────────────────────────────────────────────────────────────────────────────────
    canonical_json(bundle) = json.dumps(
        bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    bundle_hash            = engine.text_hash(canonical_json(bundle))   # "sha256:…"

  네 가지를 **전부** 고정해야 "같은 사실 → 같은 해시"가 성립한다:

  1. `sort_keys=True` — dict 는 삽입 순서를 보존하므로, 고정하지 않으면 `facts` 를 만든
     순서만 달라도 다른 해시가 난다. 서명 검증이 "근거가 바뀌었다"고 오탐하게 된다.
  2. `separators=(",", ":")` — 기본 구분자는 `", "`·`": "` 라 공백이 들어간다. 여기서
     흘린 공백은 `engine.normalize()` 가 지워 주지만(아래 4), **구분자를 고정하지 않으면
     재구현자가 공백 정책에 의존하게 된다.** 두 방어선을 겹쳐 둔다.
  3. `ensure_ascii=False` — 한글을 `\\uXXXX` 로 이스케이프하면 같은 문자열이 두 표현을
     갖는다. `engine.normalize()` 의 NFKC 는 이스케이프 시퀀스를 되돌리지 못한다.
  4. `engine.text_hash()` 재구현 금지 — 이 함수가 NFKC + 공백 정규화를 적용한다.
     계층 1 조문 해시와 **같은 규칙**이어야 "조문 해시는 A 규칙, 번들 해시는 B 규칙"
     같은 이원화가 생기지 않는다.

  ⚠ `built_at` 은 **번들 밖**에 둔다. 안에 넣으면 같은 사실도 호출할 때마다 해시가 달라져
    "근거가 변조되지 않았음"을 증명할 수 없다 — 해시의 존재 이유가 사라진다.
    같은 이유로 `evaluated_at`(판정 시각)도 번들에 싣지 않는다.
  ⚠ `laws`·`rules` 는 **리스트라 순서가 해시에 영향을 준다.** `sort_keys` 는 리스트를
    정렬해 주지 않으므로 조립 시점에 명시적으로 정렬한다(law_ref_id / rule_id·rule_version).

────────────────────────────────────────────────────────────────────────────────
★ 미수집 조문이 하나라도 있으면 **의도적으로 거부**한다 (`law_text_unavailable`)
────────────────────────────────────────────────────────────────────────────────
MQ-701(Sprint 7)에서 법제처 OPEN API 로 조문을 실수집해 **7건 중 6건이 `FETCHED`** 가 됐다.
처분 룰이 인용하는 조문은 그 6건에 전부 포함되므로 **실 DB 에서 이 도구는 이제 성공한다.**
남은 1건(`KR-CITA-ENF-31`)은 제목이 API 값과 달라 사람 승인 대기이며, 현재 어떤 룰도 인용하지 않는다.
**이 거부 경로를 지우지 말 것** — 조문이 재수집 대기로 돌아가거나 새 룰이 미수집 조문을 인용하면 즉시 다시 필요하다.

`text_hash` 가 null 인 항목을 조용히 넣고 해시하면 **해시할 사실이 없는 번들**이 나온다.
번들의 존재 이유는 "이 결정이 참조한 근거가 이후 변조되지 않았음"의 증명인데, 근거 원문이
없으면 그 증명은 빈 약속이다 — 계층 1의 존재 이유가 통째로 무너진다(`11 §2`).
`status:"error", reason:"law_text_unavailable"` + `missing_law_refs` 로 **어느 조문이
없는지 이름을 대고** 멈춘다. D50·D62 가 반복해서 막아 온 유형("없는 것을 있는 것으로
반올림하지 않는다")의 계층 1 판이다.

  판정 자체는 조문 원문 없이도 성립한다(`check_disposal_blockers` 는 `LAW_TEXT_PENDING`
  으로 정직하게 표시하고 답을 준다). **막는 것은 판정이 아니라 서명용 증빙 생성뿐**이다.

────────────────────────────────────────────────────────────────────────────────
그 밖에 지켜야 할 것
────────────────────────────────────────────────────────────────────────────────
  - ⛔ **아무것도 저장하지 않는다 (D10).** `decisions` INSERT 는 Sprint 7 의 사람 전용
    API 가 한다. 여기엔 쓰기 커넥션조차 없다 — `read_only()` 만 쓴다.
  - ⛔ **판정을 재계산하지 않는다.** verdict 5종(D79)·버킷 분류는 `check_disposal_blockers`
    를 **모듈 import 해 호출**하고 결과를 그대로 싣는다. 여기서 다시 조립하면 두 벌의
    판정 로직이 룰 개정 때 조용히 어긋난다(D73 이 엔진 복제를 기각한 것과 같은 이유).
  - **`facts` 는 반드시 `engine.build_facts()` 결과다 (D62).** `dict(row)` 를 그대로 실으면
    NULL 컬럼이 "값 있음"으로 기록돼, 서명 시점에 **모르던 사실을 알았던 것처럼** 남는다.
  - **`disposal_mode` 는 `engine.DISPOSAL_MODES` 를 단일 출처로 검증**한다. 폴백 금지.
  - **예외를 던지지 않는다 (D9·D46).** 엔진은 `RuleIntegrityError`·`KeyError`·`TypeError`
    를 던지므로 광범위하게 포착해 `status` 로 닫는다.

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
from .check_disposal_blockers import check_disposal_blockers as _judge

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

# `engine.check_disposal_blockers()` 가 돌려주는 판정 버킷 4종.
# 이 넷에 등장한 룰이 곧 "이 판정이 인용한 룰"이다 — CLEAR 자산은 넷이 전부 비어
# `rules`·`laws` 가 빈 배열이 된다. **빈 근거도 사실이므로 해시는 그대로 산출한다.**
_BUCKETS = ("blockers", "preconditions", "holds", "insufficient")

_DISCLAIMER = (
    "이 번들은 판정 시점의 근거 스냅샷이며 판정 자체가 아니다. bundle_hash 는 laws·rules·facts "
    "세 항목만을 대상으로 하며 built_at 은 포함하지 않는다(같은 사실은 언제 조립해도 같은 해시). "
    "처분 확정은 사람의 서명으로만 이뤄지고, 시스템 판정과 다른 결정은 사유 기재와 함께 기록된다."
)


def _err(reason: str, message: str, **extra: Any) -> dict:
    return {"status": "error", "reason": reason, "message": message, **extra}


def canonical_json(bundle: dict) -> str:
    """번들의 정준 직렬화. **해시를 내는 모든 곳이 이 함수 하나만 쓴다.**

    Sprint 7 의 서명 검증(`decisions.bundle_hash` 재계산)도 이 함수를 import 해서 쓸 것.
    직렬화 규약을 각자 재현하면 같은 번들에 두 해시가 생겨 검증이 무의미해진다.
    """
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_bundle_hash(bundle: dict) -> str:
    """`canonical_json` → `engine.text_hash`. 해시 함수를 재구현하지 않는다 (계층 1과 동일 규칙)."""
    return engine.text_hash(canonical_json(bundle))


def _cited_rules(judgment: dict) -> list[dict]:
    """4버킷에 등장한 룰을 `(rule_id, rule_version)` 유일키로 모아 정렬해 돌려준다.

    정렬하는 이유: 리스트 순서는 `sort_keys` 가 잡아 주지 않는데, 버킷 순회 순서가 바뀌면
    같은 근거가 다른 해시를 낸다. 유일키에 `rule_version` 을 포함하는 이유: 같은 룰의
    개정본이 공존할 수 있고(D60), **서명은 그때 그 버전에 대해 이뤄진 것**이기 때문이다.
    """
    seen: dict[tuple[str, Any], dict] = {}
    for bucket in _BUCKETS:
        for item in judgment.get(bucket) or []:
            rule_id = item.get("rule_id")
            if rule_id is None:
                continue
            rule_version = item.get("rule_version")
            seen.setdefault(
                (rule_id, rule_version), {"rule_id": rule_id, "rule_version": rule_version}
            )
    return [seen[k] for k in sorted(seen, key=lambda k: (str(k[0]), str(k[1])))]


def _cited_law_ref_ids(judgment: dict) -> list[str]:
    """인용된 룰들의 `law_refs` **합집합**(정렬). 계약 근거(`contract_refs`)는 조문이 아니다.

    조문 원문이 없는 계약 근거까지 여기서 요구하면 `여신거래기본약관`(CONTRACT 근거)이
    영원히 `law_text_unavailable` 을 만든다 — 애초에 법제처 수집 대상이 아니다.
    계약 근거는 `rules[]` 의 `rule_id` 로 카탈로그에서 되짚을 수 있다.
    """
    refs: set[str] = set()
    for bucket in _BUCKETS:
        for item in judgment.get(bucket) or []:
            for ref in item.get("law_refs") or []:
                refs.add(ref)
    return sorted(refs)


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


def _build(
    asset_id: str | None,
    equipment_id: str | None,
    disposal_mode: str,
    disposal_date: str | None,
) -> dict:
    # ── ① 판정. 재구현하지 않고 도구를 그대로 호출한다.
    #    입력 검증(문자열 여부·둘 다 없음·날짜 형식)·자산 해석·룰 카탈로그 적재 검사도
    #    전부 저쪽에 있다. 실패는 status·reason 을 **그대로 전파**한다 — 여기서 다시
    #    포장하면 같은 실패가 도구마다 다른 이름을 갖는다.
    judgment = _judge(
        asset_id=asset_id,
        equipment_id=equipment_id,
        disposal_mode=disposal_mode,
        disposal_date=disposal_date,
    )
    if judgment.get("status") != "ok":
        return judgment

    resolved_id = judgment.get("asset_id")
    # 판정에 실제로 쓰인 값을 되받아 쓴다 — 여기서 원래 인자를 다시 쓰면 정규화 결과가
    # 어긋날 때 "판정에 쓰인 사실"과 "번들에 실린 사실"이 달라진다.
    mode = judgment.get("disposal_mode", disposal_mode)
    when = judgment.get("disposal_date", disposal_date)

    cited_rules = _cited_rules(judgment)
    cited_law_ids = _cited_law_ref_ids(judgment)

    # ── ② 계층 1 사본 조회 + 사실 재조립. 읽기 전용 커넥션만 쓴다 (D10).
    with read_only() as con:
        laws = engine.load_laws_from_db(con)

        # 미등록(`laws.get() is None`)도 미수집과 같이 취급한다 — 이유는 하나다:
        # 어느 쪽이든 **해시할 원문이 없다.** 파일에는 있고 DB 사본에만 없는 상태라면
        # 그건 시드 미실행이며, `data/seed.py` ⑬ 이 먼저 잡는다.
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

        row = con.execute("SELECT * FROM assets WHERE asset_id = ?", (resolved_id,)).fetchone()
        if row is None:
            # 판정 직후에 자산이 사라진 경우(외부 재시드 등). 사실 없이 번들을 만들지 않는다.
            return _err(
                "asset_disappeared",
                f"판정 직후 자산 행을 다시 읽지 못했습니다: {resolved_id}",
                asset_id=resolved_id,
            )

        # ★ NULL 컬럼의 키를 빼는 유일한 지점 (D62). dict(row) 를 직접 싣지 않는다.
        #   판정이 쓴 것과 **같은 함수·같은 인자**라 결과도 같다.
        facts = engine.build_facts(row, disposal_mode=mode, disposal_date=when)

    bundle = {
        "laws": [_law_entry(laws[rid]) for rid in cited_law_ids],
        "rules": cited_rules,
        "facts": facts,
    }

    return {
        "status": "ok",
        "asset_id": resolved_id,
        "evidence_bundle": bundle,
        "bundle_hash": compute_bundle_hash(bundle),
        "verdict": judgment.get("verdict"),
        # 불변식 6 — `verdict` 를 최상위에 싣는 순간 소비자에게 이 응답은 **판정 결과로 읽힌다.**
        # 그러면 "무엇을 고려하지 않았는가"가 따라와야 한다.
        # ⛔ 문장을 새로 만들지 않는다. 판정 주체(`check_disposal_blockers`)가 정한 목록을
        #    **그대로** 옮긴다 — 복제하면 룰이 늘 때 두 목록이 조용히 어긋난다.
        # ⛔ 번들 **밖**이다. 안에 넣으면 목록 문구가 바뀔 때 `bundle_hash` 가 함께 흔들려
        #    "근거가 변조됐다"는 오탐이 난다. 해시 대상은 laws·rules·facts 뿐이다.
        # `.get(..., [])` 를 쓰지 않는 이유: 키가 없으면 빈 배열이 "고려에서 뺀 것이 없다"는
        #    거짓을 말한다. 없으면 차라리 실패하는 편이 낫다(래퍼가 status 로 닫는다).
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
    둘 다 비면 위임 도구가 `invalid_input` 으로 되돌린다.

    실패는 예외가 아니라 `status` 로 돌려준다 (D9·D46).
    """
    try:
        # `disposal_mode` 는 enum 단일 출처(`engine.DISPOSAL_MODES`)로 검증한다.
        # 위임 도구도 같은 검사를 하지만 **같은 상수를 보므로 어긋날 수 없고**, 여기서
        # 먼저 막으면 잘못된 mode 로 판정을 돌린 뒤 번들만 못 만드는 상태가 생기지 않는다.
        # 폴백하지 않는 이유: 'SELL' 을 'SALE' 로 고쳐 주면 오타 하나가 VAT-INVOICE 트리거를
        # 빗나가 CONDITIONAL 이어야 할 판정을 조용히 CLEAR 로 만든다.
        mode: Any = "SALE" if disposal_mode is None else disposal_mode
        if not isinstance(mode, str) or mode not in engine.DISPOSAL_MODES:
            return _err(
                "invalid_input",
                f"disposal_mode 는 {' | '.join(engine.DISPOSAL_MODES)} 중 하나여야 합니다: "
                f"{disposal_mode!r} (대소문자·유사어를 임의로 해석하지 않습니다)",
            )

        return _build(asset_id, equipment_id, mode, disposal_date)

    except engine.RuleIntegrityError as e:
        return _err("rule_integrity", f"룰 카탈로그 무결성 위반: {e}")
    except FileNotFoundError as e:
        return _err("db_missing", str(e))
    except (sqlite3.Error, OSError) as e:
        return _err("db_error", str(e))
    except Exception as e:  # noqa: BLE001 — 엔진·직렬화 예외를 status 로 바꿔 반환한다 (D9)
        return _err("internal_error", f"{type(e).__name__}: {e}")
